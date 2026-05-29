from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import requests

from app.core.config import OUTPUT_ROOT, SERVER_CONFIG_PATH, WORKSPACE_ROOT
from app.core.profiles import VoiceRegistry, first_non_empty, profile_path_text
from app.core.runtime_logs import (
    ADMIN_STDERR_LOG_PATH,
    ADMIN_STDOUT_LOG_PATH,
    DOWNLOAD_STDERR_LOG_PATH,
    DOWNLOAD_STDOUT_LOG_PATH,
    LOG_FILES,
    read_log_file,
    truncate_log,
)

ADMIN_CSS = """
.gradio-container {
  max-width: 1320px !important;
}
.neiroha-header {
  padding: 6px 0 14px 0;
  border-bottom: 1px solid var(--border-color-primary);
}
.neiroha-header h1 {
  margin: 0 0 4px 0;
  font-size: 24px;
  line-height: 1.25;
}
.neiroha-muted {
  color: var(--body-text-color-subdued);
}
.neiroha-status table,
.neiroha-table table {
  width: 100%;
  border-collapse: collapse;
}
.neiroha-status td,
.neiroha-status th,
.neiroha-table td,
.neiroha-table th {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color-primary);
}
.neiroha-status td:first-child,
.neiroha-table td:first-child {
  color: var(--body-text-color-subdued);
  width: 220px;
}
.neiroha-section {
  padding-top: 4px;
}
.neiroha-section h3 {
  margin-top: 0;
}
.neiroha-log textarea,
.neiroha-log .cm-editor {
  font-family: Consolas, "Cascadia Mono", monospace !important;
}
footer {
  display: none !important;
}
"""

TEXT = {
    "zh": {
        "title": "Neiroha CosyVoice3 Admin",
        "subtitle": "本地 CosyVoice3 推理、Voice Set、音色克隆配置与日志管理",
        "home": "首页",
        "trial": "试音",
        "voice_config": "克隆配置",
        "voice_sets": "音色集合",
        "model_presets": "模型预设",
        "download": "下载",
        "logs": "日志",
        "refresh": "刷新",
        "api_base": "API URL",
        "admin_url": "Admin URL",
        "status": "状态",
        "text": "文本",
        "model": "Voice Set",
        "voice": "Voice",
        "format": "格式",
        "speed": "语速",
        "generate": "生成",
        "audio_output": "输出音频",
        "metrics": "指标",
        "save_to_voice_set": "保存到 Voice Set",
        "model_preset": "Model Preset",
        "voice_id": "Voice ID",
        "name": "名称",
        "mode": "模式",
        "upload_reference": "上传参考音频",
        "reference_path": "参考音频路径",
        "prompt_text": "Prompt 文本",
        "instruction": "指令",
        "prompt_lang": "Prompt 语言",
        "text_lang": "文本语言",
        "save_voice": "保存 Voice",
        "save_result": "保存结果",
        "download_source": "下载源",
        "force_redownload": "强制重新下载",
        "download_base": "下载 CosyVoice3 + 前端资源",
        "download_tokenizer": "下载 wetext",
        "download_ttsfrd": "下载 ttsfrd",
        "download_status": "下载状态",
        "stop_download": "停止下载",
        "log_source": "日志源",
        "auto_refresh": "自动刷新",
        "runtime_status": "运行状态",
        "connection": "连接",
        "configuration": "配置",
        "current_language": "界面语言",
        "online": "在线",
        "offline": "离线",
        "loaded": "已加载",
        "not_loaded": "未加载",
        "preview_section": "语音预览",
        "preview_controls": "合成参数",
        "voice_identity": "音色身份",
        "reference_section": "参考音频",
        "clone_defaults": "默认参数",
        "save_success": "已保存",
        "reference_audio": "参考音频",
        "download_frontend": "前端资源",
        "log_viewer": "日志查看",
        "default_preview_text": "你好，这是 Neiroha CosyVoice3 的语音复刻测试。",
    },
    "en": {
        "title": "Neiroha CosyVoice3 Admin",
        "subtitle": "Local CosyVoice3 inference, voice sets, clone profiles, and logs",
        "home": "Home",
        "trial": "Trial",
        "voice_config": "Voice Config",
        "voice_sets": "Voice Sets",
        "model_presets": "Model Presets",
        "download": "Download",
        "logs": "Logs",
        "refresh": "Refresh",
        "api_base": "API URL",
        "admin_url": "Admin URL",
        "status": "Status",
        "text": "Text",
        "model": "Voice Set",
        "voice": "Voice",
        "format": "Format",
        "speed": "Speed",
        "generate": "Generate",
        "audio_output": "Output Audio",
        "metrics": "Metrics",
        "save_to_voice_set": "Save to Voice Set",
        "model_preset": "Model Preset",
        "voice_id": "Voice ID",
        "name": "Name",
        "mode": "Mode",
        "upload_reference": "Upload Reference",
        "reference_path": "Reference Audio Path",
        "prompt_text": "Prompt Text",
        "instruction": "Instruction",
        "prompt_lang": "Prompt Language",
        "text_lang": "Text Language",
        "save_voice": "Save Voice",
        "save_result": "Save Result",
        "download_source": "Download Source",
        "force_redownload": "Force Redownload",
        "download_base": "Download CosyVoice3 + frontend",
        "download_tokenizer": "Download wetext",
        "download_ttsfrd": "Download ttsfrd",
        "download_status": "Download Status",
        "stop_download": "Stop Download",
        "log_source": "Log Source",
        "auto_refresh": "Auto Refresh",
        "runtime_status": "Runtime Status",
        "connection": "Connection",
        "configuration": "Configuration",
        "current_language": "UI Language",
        "online": "Online",
        "offline": "Offline",
        "loaded": "Loaded",
        "not_loaded": "Not loaded",
        "preview_section": "Speech Preview",
        "preview_controls": "Synthesis",
        "voice_identity": "Voice Identity",
        "reference_section": "Reference Audio",
        "clone_defaults": "Defaults",
        "save_success": "Saved",
        "reference_audio": "Reference audio",
        "download_frontend": "Frontend",
        "log_viewer": "Log Viewer",
        "default_preview_text": "Hello, this is a Neiroha CosyVoice3 voice cloning test.",
    },
}


class DownloadManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen[str] | None = None

    def start(self, model: str, source: str, force: bool) -> str:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return "download already running"
            truncate_log(DOWNLOAD_STDOUT_LOG_PATH)
            truncate_log(DOWNLOAD_STDERR_LOG_PATH)
            command = [
                sys.executable,
                str(WORKSPACE_ROOT / "scripts" / "download_cosyvoice3_assets.py"),
                "--model",
                model,
                "--source",
                source,
            ]
            if force:
                command.append("--force")
            stdout = DOWNLOAD_STDOUT_LOG_PATH.open("w", encoding="utf-8", errors="replace")
            stderr = DOWNLOAD_STDERR_LOG_PATH.open("w", encoding="utf-8", errors="replace")
            self.process = subprocess.Popen(
                command,
                cwd=WORKSPACE_ROOT,
                text=True,
                stdout=stdout,
                stderr=stderr,
            )
            return f"started pid={self.process.pid}"

    def stop(self) -> str:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                return "no download running"
            self.process.terminate()
            return f"terminated pid={self.process.pid}"

    def status(self) -> str:
        with self.lock:
            if self.process is None:
                state = "idle"
            else:
                code = self.process.poll()
                state = f"running pid={self.process.pid}" if code is None else f"exited code={code}"
        stdout = read_log_file(DOWNLOAD_STDOUT_LOG_PATH, limit=80, newest_first=True)
        stderr = read_log_file(DOWNLOAD_STDERR_LOG_PATH, limit=80, newest_first=True)
        return f"{state}\n\n[download.out.log]\n{stdout}\n\n[download.err.log]\n{stderr}"


download_manager = DownloadManager()


def _language(registry: VoiceRegistry) -> str:
    configured = os.environ.get("NEIROHA_COSYVOICE3_UI_LANG", "")
    if not configured:
        ui_config = registry.server_config().get("ui", {})
        configured = ui_config.get("default_language", "zh") if isinstance(ui_config, dict) else "zh"
    return configured if configured in TEXT else "zh"


def _ui_title(registry: VoiceRegistry, text: dict[str, str]) -> str:
    ui_config = registry.server_config().get("ui", {})
    configured = ui_config.get("title", "") if isinstance(ui_config, dict) else ""
    return first_non_empty(configured, text["title"])


def _api_get(api_base: str, path: str) -> dict[str, Any]:
    response = requests.get(f"{api_base.rstrip('/')}{path}", timeout=5)
    response.raise_for_status()
    return response.json()


def _voice_sets(registry: VoiceRegistry) -> list[str]:
    return [voice_set.id for voice_set in registry.list_voice_sets()]


def _voices(registry: VoiceRegistry, voice_set_id: str) -> list[str]:
    return [profile.id for profile in registry.list_profiles(voice_set_id)]


def _format_status(api_base: str, admin_url: str, registry: VoiceRegistry, text: dict[str, str], language: str) -> str:
    try:
        health = _api_get(api_base, "/health")
        api_state = text["online"]
        loaded = health.get("model_loaded")
        device = health.get("device", "")
        sample_rate = health.get("sample_rate", "")
    except Exception as exc:
        api_state = f"{text['offline']} ({exc})"
        loaded = False
        device = ""
        sample_rate = ""
    profiles = registry.list_profiles(registry.active_voice_set_id())
    loaded_text = text["loaded"] if loaded else text["not_loaded"]
    rows = [
        ("API", api_state),
        ("API URL", api_base),
        ("Admin URL", admin_url),
        (text["current_language"], language),
        ("Server config", profile_path_text(SERVER_CONFIG_PATH)),
        ("Model preset", registry.active_model_preset_id()),
        ("Voice set", registry.active_voice_set_id()),
        ("Default voice", registry.default_voice_id()),
        ("Model", loaded_text),
        ("Sample rate", sample_rate),
        ("Device", device),
        ("Voices", len(profiles)),
        ("PID", os.getpid()),
    ]
    table = ["| Key | Value |", "| --- | --- |"]
    table.extend(f"| {key} | {value} |" for key, value in rows)
    return "\n".join(table)


def _format_voice_sets(registry: VoiceRegistry) -> str:
    rows = ["| id | name | voices |", "| --- | --- | --- |"]
    for voice_set in registry.list_voice_sets():
        rows.append(f"| {voice_set.id} | {voice_set.name} | {', '.join(voice_set.voices)} |")
    return "\n".join(rows)


def _format_model_presets(registry: VoiceRegistry) -> str:
    rows = ["| id | name | model_dir | fp16 |", "| --- | --- | --- | --- |"]
    for preset in registry.list_model_presets():
        rows.append(f"| {preset.id} | {preset.name} | {profile_path_text(preset.model_dir)} | {preset.fp16} |")
    return "\n".join(rows)


def build_gradio_admin_blocks(
    *,
    api_base: str,
    admin_url: str = "",
    registry: VoiceRegistry | None = None,
):
    import gradio as gr

    registry = registry or VoiceRegistry()
    lang = _language(registry)
    text = TEXT[lang]
    ui_title = _ui_title(registry, text)

    def t(key: str) -> str:
        return text.get(key, key)

    initial_voice_set = registry.active_voice_set_id()
    initial_voices = _voices(registry, initial_voice_set)
    initial_voice = registry.default_voice_id() if registry.default_voice_id() in initial_voices else (initial_voices[0] if initial_voices else "")
    model_preset_ids = [preset.id for preset in registry.list_model_presets()]

    def refresh_home() -> str:
        return _format_status(api_base, admin_url, registry, text, lang)

    def refresh_voice_dropdown(voice_set_id: str):
        voices = _voices(registry, voice_set_id)
        return gr.update(choices=voices, value=voices[0] if voices else "")

    def refresh_choices():
        voice_sets = _voice_sets(registry)
        selected_set = registry.active_voice_set_id() if registry.active_voice_set_id() in voice_sets else (voice_sets[0] if voice_sets else "")
        voices = _voices(registry, selected_set)
        return (
            gr.update(choices=voice_sets, value=selected_set),
            gr.update(choices=voices, value=voices[0] if voices else ""),
        )

    def synthesize_preview(model: str, voice: str, input_text: str, response_format: str, speed: float):
        try:
            payload = {
                "model": model,
                "voice": voice,
                "input": input_text,
                "response_format": response_format,
                "speed": speed,
            }
            response = requests.post(f"{api_base.rstrip('/')}/v1/audio/speech", json=payload, timeout=180)
            response.raise_for_status()
            extension = response_format or "wav"
            path = OUTPUT_ROOT / f"admin_preview_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
            path.write_bytes(response.content)
            metrics = {
                "output": profile_path_text(path),
                "audio_seconds": response.headers.get("X-Neiroha-Audio-Seconds", ""),
                "elapsed_seconds": response.headers.get("X-Neiroha-Elapsed-Seconds", ""),
                "rtf": response.headers.get("X-Neiroha-RTF", ""),
                "server_output": response.headers.get("X-Neiroha-Output-Path", ""),
            }
            return str(path), json.dumps(metrics, ensure_ascii=False, indent=2)
        except Exception as exc:
            return None, str(exc)

    def save_voice(
        voice_set_id: str,
        model_preset: str,
        voice_id: str,
        name: str,
        mode: str,
        uploaded_reference: str | None,
        reference_path: str,
        prompt_text: str,
        prompt_lang: str,
        text_lang: str,
        instruction: str,
        speed: float,
    ):
        try:
            profile = registry.save_voice_profile(
                voice_set_id=voice_set_id,
                model_preset=model_preset,
                voice_id=voice_id,
                name=name,
                mode=mode,
                reference_audio=reference_path,
                prompt_text=prompt_text,
                prompt_lang=prompt_lang,
                text_lang=text_lang,
                instruction=instruction,
                speed=speed,
                upload_path=uploaded_reference or "",
            )
            voice_sets = _voice_sets(registry)
            voices = _voices(registry, voice_set_id)
            status = f"{t('save_success')}: {profile.id}\n{t('reference_audio')}: {profile_path_text(profile.prompt_audio_path)}"
            return (
                status,
                _format_voice_sets(registry),
                gr.update(choices=voice_sets, value=voice_set_id),
                gr.update(choices=voices, value=profile.id),
            )
        except Exception as exc:
            return str(exc), _format_voice_sets(registry), gr.update(), gr.update()

    def read_selected_log(name: str) -> str:
        return read_log_file(LOG_FILES.get(name, LOG_FILES["backend.log"]), limit=220, newest_first=True)

    with gr.Blocks(
        title=ui_title,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=ADMIN_CSS,
    ) as blocks:
        gr.Markdown(
            f"# {ui_title}\n<span class='neiroha-muted'>{t('subtitle')}</span>",
            elem_classes=["neiroha-header"],
        )
        with gr.Tab(t("home")):
            status_box = gr.Markdown(
                value=refresh_home(),
                label=t("runtime_status"),
                elem_classes=["neiroha-status"],
            )
            refresh_btn = gr.Button(t("refresh"), variant="secondary")
            refresh_btn.click(refresh_home, outputs=status_box)
            home_timer = gr.Timer(value=2.0, active=True)
            home_timer.tick(refresh_home, outputs=status_box)

        with gr.Tab(t("trial")):
            with gr.Row():
                with gr.Column(scale=2, elem_classes=["neiroha-section"]):
                    gr.Markdown(f"### {t('preview_section')}")
                    trial_text = gr.Textbox(value=t("default_preview_text"), label=t("text"), lines=5)
                    with gr.Row():
                        model_dropdown = gr.Dropdown(choices=_voice_sets(registry), value=initial_voice_set, label=t("model"))
                        voice_dropdown = gr.Dropdown(choices=initial_voices, value=initial_voice, label=t("voice"))
                        refresh_choices_btn = gr.Button(t("refresh"), variant="secondary")
                    with gr.Row():
                        format_dropdown = gr.Dropdown(choices=["wav", "mp3", "flac", "aac", "opus", "ogg", "pcm", "raw"], value="wav", label=t("format"))
                        speed_slider = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label=t("speed"))
                        synth_btn = gr.Button(t("generate"), variant="primary")
                with gr.Column(scale=1, elem_classes=["neiroha-section"]):
                    gr.Markdown(f"### {t('metrics')}")
                    audio_output = gr.Audio(type="filepath", label=t("audio_output"), autoplay=False)
                    metrics_box = gr.Code(label=t("metrics"), language="json", lines=8)
            model_dropdown.change(refresh_voice_dropdown, inputs=model_dropdown, outputs=voice_dropdown)
            refresh_choices_btn.click(refresh_choices, outputs=[model_dropdown, voice_dropdown])
            synth_btn.click(
                synthesize_preview,
                inputs=[model_dropdown, voice_dropdown, trial_text, format_dropdown, speed_slider],
                outputs=[audio_output, metrics_box],
            )

        with gr.Tab(t("voice_config")):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown(f"### {t('voice_identity')}")
                    clone_voice_set = gr.Dropdown(choices=_voice_sets(registry), value=initial_voice_set, label=t("save_to_voice_set"))
                    clone_model_preset = gr.Dropdown(choices=model_preset_ids, value=model_preset_ids[0] if model_preset_ids else "", label=t("model_preset"))
                    clone_mode = gr.Dropdown(choices=["prompt_clone", "cross_lingual", "instruct"], value="prompt_clone", label=t("mode"))
                    clone_voice_id = gr.Textbox(value="local-voice", label=t("voice_id"))
                    clone_voice_name = gr.Textbox(value="Local Voice", label=t("name"))
                with gr.Column(scale=1):
                    gr.Markdown(f"### {t('reference_section')}")
                    clone_ref_file = gr.Audio(type="filepath", label=t("upload_reference"))
                    clone_ref_path = gr.Textbox(label=t("reference_path"))
                    clone_prompt_text = gr.Textbox(label=t("prompt_text"), lines=2)
                    clone_instruction = gr.Textbox(label=t("instruction"), lines=2)
                with gr.Column(scale=1):
                    gr.Markdown(f"### {t('clone_defaults')}")
                    clone_prompt_lang = gr.Textbox(value="zh", label=t("prompt_lang"))
                    clone_text_lang = gr.Textbox(value="zh", label=t("text_lang"))
                    clone_speed = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label=t("speed"))
                    save_voice_btn = gr.Button(t("save_voice"), variant="primary")
                    save_voice_status = gr.Textbox(label=t("save_result"), lines=4)
            voice_sets_box = gr.Markdown(value=_format_voice_sets(registry), elem_classes=["neiroha-table"])
            save_voice_btn.click(
                save_voice,
                inputs=[
                    clone_voice_set,
                    clone_model_preset,
                    clone_voice_id,
                    clone_voice_name,
                    clone_mode,
                    clone_ref_file,
                    clone_ref_path,
                    clone_prompt_text,
                    clone_prompt_lang,
                    clone_text_lang,
                    clone_instruction,
                    clone_speed,
                ],
                outputs=[save_voice_status, voice_sets_box, model_dropdown, voice_dropdown],
            )

        with gr.Tab(t("voice_sets")):
            voice_sets_markdown = gr.Markdown(value=_format_voice_sets(registry), elem_classes=["neiroha-table"])
            gr.Button(t("refresh"), variant="secondary").click(lambda: _format_voice_sets(registry), outputs=voice_sets_markdown)

        with gr.Tab(t("model_presets")):
            presets_markdown = gr.Markdown(value=_format_model_presets(registry), elem_classes=["neiroha-table"])
            gr.Button(t("refresh"), variant="secondary").click(lambda: _format_model_presets(registry), outputs=presets_markdown)

        with gr.Tab(t("download")):
            with gr.Row():
                download_source = gr.Dropdown(choices=["modelscope", "hf", "hf-mirror"], value="modelscope", label=t("download_source"))
                download_force = gr.Checkbox(value=False, label=t("force_redownload"))
            with gr.Row():
                download_base_btn = gr.Button(t("download_base"))
                download_tokenizer_btn = gr.Button(t("download_tokenizer"))
                download_ttsfrd_btn = gr.Button(t("download_ttsfrd"))
                download_stop_btn = gr.Button(t("stop_download"))
                download_refresh_btn = gr.Button(t("refresh"))
            download_status = gr.Textbox(value=download_manager.status(), label=t("download_status"), lines=22)
            download_base_btn.click(lambda source, force: download_manager.start("cosyvoice3", source, force), inputs=[download_source, download_force], outputs=download_status)
            download_tokenizer_btn.click(lambda source, force: download_manager.start("wetext", source, force), inputs=[download_source, download_force], outputs=download_status)
            download_ttsfrd_btn.click(lambda source, force: download_manager.start("ttsfrd", source, force), inputs=[download_source, download_force], outputs=download_status)
            download_stop_btn.click(download_manager.stop, outputs=download_status)
            download_refresh_btn.click(download_manager.status, outputs=download_status)

        with gr.Tab(t("logs")):
            gr.Markdown(f"### {t('log_viewer')}")
            log_source = gr.Dropdown(choices=list(LOG_FILES), value="backend.log", label=t("log_source"))
            with gr.Row():
                auto_refresh = gr.Checkbox(value=True, label=t("auto_refresh"))
                log_refresh_btn = gr.Button(t("refresh"), variant="secondary")
            log_box = gr.Textbox(value=read_selected_log("backend.log"), label=t("logs"), lines=30, elem_classes=["neiroha-log"])
            log_refresh_btn.click(read_selected_log, inputs=log_source, outputs=log_box)
            log_source.change(read_selected_log, inputs=log_source, outputs=log_box)
            log_timer = gr.Timer(value=2.0, active=True)
            log_timer.tick(lambda enabled, name: read_selected_log(name) if enabled else gr.update(), inputs=[auto_refresh, log_source], outputs=log_box)

    return blocks.queue(max_size=8, default_concurrency_limit=1)


def build_gradio_blocks(runtime: Any = None, registry: VoiceRegistry | None = None):
    registry = registry or VoiceRegistry()
    server_config = registry.server_config()
    api_config = server_config.get("api", {}) if isinstance(server_config.get("api"), dict) else {}
    admin_config = server_config.get("admin", {}) if isinstance(server_config.get("admin"), dict) else {}
    api_host = api_config.get("host", "127.0.0.1")
    api_port = int(api_config.get("port", 19890))
    admin_host = admin_config.get("host", "127.0.0.1")
    admin_port = int(admin_config.get("port", 17870))
    api_base = os.environ.get("NEIROHA_COSYVOICE3_API_BASE", f"http://{api_host}:{api_port}")
    admin_url = os.environ.get("NEIROHA_COSYVOICE3_ADMIN_URL", f"http://{admin_host}:{admin_port}")
    return build_gradio_admin_blocks(api_base=api_base, admin_url=admin_url, registry=registry)
