from __future__ import annotations

import datetime as dt
import hashlib
import re
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from fastapi.responses import JSONResponse, Response

from app.core.config import OUTPUT_ROOT, UPLOAD_ROOT, WORKSPACE_ROOT
from app.core.profiles import first_non_empty, normalize_mode_name, strip_text
from app.core.runtime_logs import RUNTIME_EVENTS
from app.core.schemas import CosyVoiceSpeechRequest
from app.services.audio import pack_audio
from app.services.cosyvoice_runtime import SynthesisInput, SynthesisResult


def json_response(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code)


def openai_error(
    message: str,
    *,
    status_code: int = 400,
    error_type: str = "invalid_request_error",
    code: str = "invalid_request",
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "type": error_type,
                "param": None,
            }
        },
    )


def classify_error_code(message: str) -> str:
    lowered = message.lower()
    if "response_format" in lowered or "unsupported" in lowered:
        return "unsupported_format"
    if "model preset" in lowered:
        return "model_preset_not_found"
    if "voice set" in lowered or "未找到 voice set" in message:
        return "voice_not_found"
    if "未找到角色" in message or "profile" in lowered or "voice" in lowered:
        return "voice_not_found"
    if "prompt_audio" in lowered or "reference" in lowered or "audio" in lowered:
        return "invalid_reference_audio"
    if "model" in lowered and "load" in lowered:
        return "model_not_loaded"
    return "invalid_request"


def extract_voice_name(value: Any) -> str:
    if isinstance(value, dict):
        return first_non_empty(value.get("id"), value.get("voice_id"), value.get("name"))
    return strip_text(value)


def require_existing_file(raw_path: str, *, field_name: str) -> str:
    path_text = strip_text(raw_path)
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{field_name} does not exist: {raw_path}")
    return str(path.resolve())


def safe_ascii_filename_part(value: Any, fallback: str = "speech") -> str:
    raw = strip_text(value) or fallback
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw)
    text = re.sub(r"\s+", "_", text).strip("._- ")
    ascii_text = text.encode("ascii", errors="ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("._-")
    if ascii_text:
        return ascii_text[:80]
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{fallback}_{digest}"


def workspace_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def header_value(value: Any) -> str:
    text = strip_text(value)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return urllib.parse.quote(text, safe="")


def write_runtime_output(content: bytes, voice_name: str, extension: str) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    stem = safe_ascii_filename_part(voice_name, fallback="speech")
    path = OUTPUT_ROOT / f"{stem}_{timestamp}.{extension}"
    counter = 1
    while path.exists():
        path = OUTPUT_ROOT / f"{stem}_{timestamp}_{counter}.{extension}"
        counter += 1
    path.write_bytes(content)
    return path


async def save_uploaded_audio(uploaded_audio: UploadFile | None, *, prefix: str = "prompt") -> str:
    if uploaded_audio is None or not uploaded_audio.filename:
        return ""
    suffix = Path(uploaded_audio.filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=UPLOAD_ROOT,
        prefix=f"{prefix}_",
        suffix=suffix,
    ) as tmp:
        tmp.write(await uploaded_audio.read())
        return tmp.name


def cleanup_temp_file(path: str) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def audio_response(result: SynthesisResult, response_format: str) -> Response:
    packed = pack_audio(result.audio, result.sample_rate, response_format)
    output_path = write_runtime_output(packed.content, result.voice_name or result.mode, packed.extension)
    output_relative = workspace_relative_path(output_path)
    filename = output_path.name
    RUNTIME_EVENTS.append(
        "synthesis_complete",
        voice=result.voice_name or result.mode,
        mode=result.mode,
        audio_seconds=result.audio_seconds,
        elapsed_seconds=result.elapsed_seconds,
        rtf=result.rtf,
        output=output_relative,
    )
    output_format = (response_format or packed.extension).strip().lower()
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Neiroha-Backend": result.backend,
        "X-Neiroha-Model-Preset": result.model_preset,
        "X-Neiroha-Voice": header_value(result.voice_id or result.voice_name),
        "X-Neiroha-Sample-Rate": str(result.sample_rate),
        "X-Neiroha-Inference-Ms": str(int(result.elapsed_seconds * 1000)),
        "X-Neiroha-Output-Format": output_format,
        "X-Neiroha-Output-Path": output_relative,
        "X-Neiroha-Audio-Seconds": f"{result.audio_seconds:.6f}",
        "X-Neiroha-Elapsed-Seconds": f"{result.elapsed_seconds:.6f}",
        "X-Neiroha-RTF": f"{result.rtf:.6f}",
        "X-Neiroha-CosyVoice-Mode": result.mode,
    }
    return Response(
        content=packed.content,
        media_type=packed.media_type,
        headers={key: value for key, value in headers.items() if value != ""},
    )


def infer_mode(payload: CosyVoiceSpeechRequest, *, prompt_audio: str, prompt_text: str, instruct_text: str) -> str:
    requested = normalize_mode_name(payload.mode)
    if requested:
        return requested
    if instruct_text and prompt_audio:
        return "instruct"
    if prompt_text and prompt_audio:
        return "zero_shot"
    if prompt_audio:
        return "cross_lingual"
    return ""


def payload_text(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(payload.text, payload.input)


def payload_response_format(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(payload.response_format, payload.format, "wav").lower()


def payload_prompt_audio(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(
        payload.prompt_audio_path,
        payload.reference_audio_path,
        payload.ref_audio_path,
    )


def payload_prompt_text(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(payload.prompt_text, payload.reference_text)


def payload_instruct_text(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(
        payload.instruct_text,
        payload.instruction_text,
        payload.instructions,
        payload.voice_instruction,
    )


def payload_profile_name(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(
        payload.profile,
        payload.character_name,
        payload.speaker,
        extract_voice_name(payload.voice),
    )


def payload_sft_spk(payload: CosyVoiceSpeechRequest) -> str:
    return first_non_empty(payload.sft_spk, payload.spk_id)


def payload_voice_set_id(payload: CosyVoiceSpeechRequest, registry) -> str:
    requested = strip_text(payload.model)
    if not requested or requested in {"cosyvoice", "cosyvoice-openai-tts", "tts-1", "tts-1-hd"}:
        return registry.active_voice_set_id()
    return requested


def build_synthesis_input(
    payload: CosyVoiceSpeechRequest,
    *,
    registry,
    uploaded_prompt_audio: str = "",
    strict_profile: bool = True,
) -> SynthesisInput:
    text = payload_text(payload)
    if not text:
        raise ValueError("text/input is required.")

    voice_set_id = payload_voice_set_id(payload, registry)
    try:
        voice_set = registry.get_voice_set(voice_set_id)
    except KeyError as exc:
        raise ValueError(f"未找到 voice set: {voice_set_id}") from exc

    profile_name = payload_profile_name(payload)
    profile = registry.get_optional(profile_name, voice_set_id=voice_set.id) if profile_name else None

    request_prompt_audio = uploaded_prompt_audio or payload_prompt_audio(payload)
    has_ad_hoc_prompt_audio = bool(request_prompt_audio)
    if profile_name and profile is None and (strict_profile or not has_ad_hoc_prompt_audio):
        raise ValueError(f"未找到角色: {profile_name}")

    prompt_audio = first_non_empty(request_prompt_audio, profile.prompt_audio_path if profile else "")
    prompt_text = first_non_empty(payload_prompt_text(payload), profile.prompt_text if profile else "")
    instruct_text = first_non_empty(payload_instruct_text(payload), profile.instruct_text if profile else "")
    sft_spk = first_non_empty(payload_sft_spk(payload), profile.sft_spk if profile else "")
    mode = infer_mode(payload, prompt_audio=prompt_audio, prompt_text=prompt_text, instruct_text=instruct_text)
    if not mode and profile is not None:
        mode = profile.engine_mode
    if not mode:
        raise ValueError("mode is required, or provide profile/prompt fields that imply a mode.")

    if prompt_audio:
        prompt_audio = require_existing_file(prompt_audio, field_name="prompt_audio")

    return SynthesisInput(
        text=text,
        mode=mode,
        prompt_audio=prompt_audio,
        prompt_text=prompt_text,
        instruct_text=instruct_text,
        sft_spk=sft_spk,
        speed=float(payload.speed or (profile.speed if profile else 1.0) or 1.0),
        seed=payload.seed,
        text_frontend=bool(payload.text_frontend),
        voice_name=profile.id if profile else profile_name,
        voice_set=voice_set.id,
        model_preset=profile.model_preset if profile else registry.active_model_preset_id(),
        voice_id=profile.id if profile else profile_name,
    )
