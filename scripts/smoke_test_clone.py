from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.core.config import DEFAULT_MODEL_DIR, DEFAULT_REPO_DIR, OUTPUT_ROOT, prepare_runtime_environment
from app.services.audio import pack_audio
from app.services.cosyvoice_runtime import CosyVoiceRuntime, SynthesisInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real CosyVoice3 zero-shot clone smoke test.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--prompt-audio", type=Path, default=DEFAULT_REPO_DIR / "asset" / "zero_shot_prompt.wav")
    parser.add_argument("--prompt-text", default="希望你以后能够做的比我还好呦。")
    parser.add_argument("--text", default="你好，这是 Neiroha CosyVoice3 的语音克隆测试。")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT / "cosyvoice3_clone_smoke.wav")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def resolve_workspace_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (WORKSPACE_ROOT / path).resolve()


def main() -> None:
    prepare_runtime_environment()
    args = parse_args()
    model_dir = resolve_workspace_path(args.model_dir)
    repo_dir = resolve_workspace_path(args.repo_dir)
    prompt_audio = resolve_workspace_path(args.prompt_audio)
    output = resolve_workspace_path(args.output)

    if not prompt_audio.exists():
        raise FileNotFoundError(f"Prompt audio does not exist: {prompt_audio}")
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory does not exist: {model_dir}")

    runtime = CosyVoiceRuntime(model_dir=model_dir, repo_dir=repo_dir)
    result = runtime.synthesize(
        SynthesisInput(
            text=args.text,
            mode="zero_shot",
            prompt_audio=str(prompt_audio),
            prompt_text=args.prompt_text,
            speed=args.speed,
            seed=args.seed,
            voice_name="smoke-test",
        )
    )
    packed = pack_audio(result.audio, result.sample_rate, "wav")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(packed.content)
    print(
        "CosyVoice3 clone smoke test passed: "
        f"{output} audio_seconds={result.audio_seconds:.2f} "
        f"elapsed_seconds={result.elapsed_seconds:.2f} rtf={result.rtf:.4f}"
    )


if __name__ == "__main__":
    main()
