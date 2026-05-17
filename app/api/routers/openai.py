from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import (
    audio_response,
    build_synthesis_input,
    openai_error,
    payload_prompt_audio,
    payload_response_format,
)
from app.api.dependencies import get_runtime, get_voice_registry
from app.core.profiles import VoiceRegistry, first_non_empty
from app.core.schemas import OpenAISpeechRequest
from app.services.cosyvoice_runtime import CosyVoiceRuntime

router = APIRouter(tags=["openai"])

OPENAI_MODEL_ALIAS = "cosyvoice-openai-tts"


@router.get("/v1/models", summary="List available models")
@router.get("/models", include_in_schema=False)
def list_models(runtime: CosyVoiceRuntime = Depends(get_runtime)):
    return {
        "object": "list",
        "data": [
            {"id": OPENAI_MODEL_ALIAS, "object": "model", "owned_by": "neiroha"},
            {"id": "tts-1", "object": "model", "owned_by": "openai-compatible", "root_model": OPENAI_MODEL_ALIAS},
            {"id": runtime.model_id, "object": "model", "owned_by": "local"},
        ],
    }


@router.get("/v1/audio/voices", summary="List voices (OpenAI-compatible extension)")
@router.get("/v1/audio/speakers", include_in_schema=False)
@router.get("/audio/voices", include_in_schema=False)
def list_voices(registry: VoiceRegistry = Depends(get_voice_registry)):
    voices = [profile.to_openai_voice_item() for profile in registry.list_profiles()]
    return {"object": "list", "data": voices, "voices": voices}


@router.post("/v1/audio/speech", summary="Generate speech (OpenAI compatible)")
@router.post("/audio/speech", include_in_schema=False)
def openai_speech(
    payload: OpenAISpeechRequest,
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    try:
        voice_name = first_non_empty(
            payload.profile,
            payload.character_name,
            payload.speaker,
            payload.voice if isinstance(payload.voice, str) else "",
        )
        if voice_name in {"default", "clone", "ad-hoc"} and payload_prompt_audio(payload):
            payload.voice = None
            payload.profile = None
            payload.speaker = None
            payload.character_name = None
        synthesis_input = build_synthesis_input(payload, registry=registry, strict_profile=True)
        result = runtime.synthesize(synthesis_input)
        return audio_response(result, payload_response_format(payload))
    except FileNotFoundError as exc:
        return openai_error(str(exc), status_code=404)
    except ValueError as exc:
        message = str(exc)
        status = 404 if message.startswith("未找到角色") else 400
        return openai_error(message, status_code=status)
    except Exception as exc:
        return openai_error(str(exc), status_code=500, error_type="server_error")

