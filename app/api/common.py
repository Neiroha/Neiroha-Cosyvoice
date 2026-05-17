from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from fastapi.responses import JSONResponse, Response

from app.core.config import UPLOAD_ROOT
from app.core.profiles import first_non_empty, normalize_mode_name, strip_text
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
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": None}},
    )


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
    return Response(
        content=packed.content,
        media_type=packed.media_type,
        headers={
            "Content-Disposition": f'inline; filename="speech.{packed.extension}"',
            "X-Neiroha-Audio-Seconds": f"{result.audio_seconds:.6f}",
            "X-Neiroha-Elapsed-Seconds": f"{result.elapsed_seconds:.6f}",
            "X-Neiroha-RTF": f"{result.rtf:.6f}",
            "X-Neiroha-CosyVoice-Mode": result.mode,
        },
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

    profile_name = payload_profile_name(payload)
    profile = registry.get_optional(profile_name) if profile_name else None

    request_prompt_audio = uploaded_prompt_audio or payload_prompt_audio(payload)
    has_ad_hoc_prompt_audio = bool(request_prompt_audio)
    if profile_name and profile is None and (strict_profile or not has_ad_hoc_prompt_audio):
        raise ValueError(f"未找到角色: {profile_name}")

    prompt_audio = first_non_empty(request_prompt_audio, profile.prompt_audio if profile else "")
    prompt_text = first_non_empty(payload_prompt_text(payload), profile.prompt_text if profile else "")
    instruct_text = first_non_empty(payload_instruct_text(payload), profile.instruct_text if profile else "")
    sft_spk = first_non_empty(payload_sft_spk(payload), profile.sft_spk if profile else "")
    mode = infer_mode(payload, prompt_audio=prompt_audio, prompt_text=prompt_text, instruct_text=instruct_text)
    if not mode and profile is not None:
        mode = profile.mode
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
        speed=float(payload.speed or 1.0),
        seed=payload.seed,
        text_frontend=bool(payload.text_frontend),
        voice_name=profile.name if profile else profile_name,
    )

