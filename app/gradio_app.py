from __future__ import annotations

import json
from typing import Any

from app.core.profiles import VoiceRegistry, first_non_empty, normalize_mode_name
from app.services.audio import normalize_audio_array
from app.services.cosyvoice_runtime import CosyVoiceRuntime, SynthesisInput


def build_gradio_blocks(runtime: CosyVoiceRuntime, registry: VoiceRegistry):
    import gradio as gr

    def profile_choices() -> list[str]:
        return [""] + [profile.id for profile in registry.list_profiles()]

    def profiles_json() -> str:
        return json.dumps(
            {"profiles": [profile.to_profile_item() for profile in registry.list_profiles()]},
            ensure_ascii=False,
            indent=2,
        )

    def refresh_profiles():
        choices = profile_choices()
        return gr.update(choices=choices, value=choices[0]), profiles_json()

    def synthesize(
        text: str,
        mode: str,
        profile_id: str,
        prompt_audio_file: str | None,
        prompt_audio_path: str,
        prompt_text: str,
        instruct_text: str,
        sft_spk: str,
        speed: float,
        seed: float | None,
    ) -> tuple[tuple[int, Any] | None, str]:
        try:
            profile = registry.get_optional(profile_id)
            resolved_mode = normalize_mode_name(mode)
            prompt_audio = first_non_empty(
                prompt_audio_file,
                prompt_audio_path,
                profile.prompt_audio if profile else "",
            )
            request = SynthesisInput(
                text=first_non_empty(text),
                mode=resolved_mode or (profile.mode if profile else ""),
                prompt_audio=prompt_audio,
                prompt_text=first_non_empty(prompt_text, profile.prompt_text if profile else ""),
                instruct_text=first_non_empty(instruct_text, profile.instruct_text if profile else ""),
                sft_spk=first_non_empty(sft_spk, profile.sft_spk if profile else ""),
                speed=float(speed or 1.0),
                seed=int(seed) if seed is not None else None,
                voice_name=profile.name if profile else profile_id,
            )
            result = runtime.synthesize(request)
            audio = normalize_audio_array(result.audio)
            status = (
                f"mode={result.mode}, audio={result.audio_seconds:.2f}s, "
                f"elapsed={result.elapsed_seconds:.2f}s, rtf={result.rtf:.4f}"
            )
            return (result.sample_rate, audio), status
        except Exception as exc:
            return None, str(exc)

    with gr.Blocks(title="Neiroha CosyVoice") as blocks:
        gr.Markdown("## Neiroha CosyVoice")
        with gr.Row():
            with gr.Column(scale=2):
                text = gr.Textbox(
                    label="Text",
                    lines=4,
                    value="你好，欢迎使用 Neiroha CosyVoice。",
                )
                with gr.Row():
                    mode = gr.Dropdown(
                        choices=["zero_shot", "cross_lingual", "instruct", "sft"],
                        value="zero_shot",
                        label="Mode",
                    )
                    profile = gr.Dropdown(choices=profile_choices(), value="", label="Profile")
                    speed = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="Speed")
                    seed = gr.Number(value=None, label="Seed", precision=0)
                prompt_audio_file = gr.Audio(type="filepath", label="Prompt Audio Upload")
                prompt_audio_path = gr.Textbox(label="Prompt Audio Path")
                prompt_text = gr.Textbox(label="Prompt Text", lines=2)
                instruct_text = gr.Textbox(label="Instruct Text", lines=2)
                sft_spk = gr.Textbox(label="SFT Speaker")
                generate_btn = gr.Button("Generate", variant="primary")
            with gr.Column(scale=1):
                audio_output = gr.Audio(label="Output", autoplay=True)
                status = gr.Textbox(label="Status", lines=3)
                profiles_box = gr.Code(value=profiles_json(), language="json", label="Profiles")
                refresh_btn = gr.Button("Refresh Profiles")

        generate_btn.click(
            synthesize,
            inputs=[
                text,
                mode,
                profile,
                prompt_audio_file,
                prompt_audio_path,
                prompt_text,
                instruct_text,
                sft_spk,
                speed,
                seed,
            ],
            outputs=[audio_output, status],
        )
        refresh_btn.click(refresh_profiles, outputs=[profile, profiles_box])

    return blocks.queue(max_size=8, default_concurrency_limit=1)

