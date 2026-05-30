from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.api.common import (
    audio_response,
    build_synthesis_input,
    classify_error_code,
    cleanup_temp_file,
    openai_error,
    payload_response_format,
    save_uploaded_audio,
)
from app.api.dependencies import get_runtime, get_voice_registry
from app.core.profiles import MODE_ALIASES, MODE_LABELS, VoiceRegistry
from app.core.runtime_logs import LOG_FILES, RUNTIME_EVENTS, read_log_file
from app.core.schemas import CosyVoiceSpeechRequest
from app.services.audio import CONTENT_TYPES
from app.services.cosyvoice_runtime import CosyVoiceRuntime

router = APIRouter(tags=["cosyvoice"])


def _profile_items(registry: VoiceRegistry) -> list[dict[str, object]]:
    return [profile.to_profile_item() for profile in registry.list_profiles()]


def _speaker_items(registry: VoiceRegistry) -> list[dict[str, object]]:
    return [profile.to_speaker_item() for profile in registry.list_profiles()]


@router.get("/api/cosyvoice/voices", summary="List registered CosyVoice voices")
@router.get("/api/cosyvoice/profiles", include_in_schema=False)
@router.get("/cosyvoice/profiles", summary="List registered CosyVoice profiles")
@router.get("/cosyvoice3/profiles", include_in_schema=False)
def cosyvoice_profiles(registry: VoiceRegistry = Depends(get_voice_registry)):
    return {
        "object": "list",
        "data": _profile_items(registry),
        "voice_sets": [voice_set.to_openai_model(len(registry.list_profiles(voice_set.id))) for voice_set in registry.list_voice_sets()],
    }


@router.get("/api/cosyvoice/meta", summary="Describe native CosyVoice capabilities")
@router.get("/api/cosyvoice/capabilities", include_in_schema=False)
@router.get("/cosyvoice/meta", include_in_schema=False)
@router.get("/cosyvoice3/meta", include_in_schema=False)
@router.get("/cosyvoice3/capabilities", include_in_schema=False)
def cosyvoice_meta(
    request: Request,
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    api_url = getattr(request.app.state, "api_url", "")
    admin_url = getattr(request.app.state, "admin_url", "")
    return {
        "provider": "cosyvoice3",
        "model": runtime.model_id,
        "model_loaded": runtime.model_loaded,
        "api_url": api_url,
        "admin_url": admin_url,
        "runtime": {
            "active_model_preset": registry.active_model_preset_id(),
            "active_voice_set": registry.active_voice_set_id(),
            "default_voice": registry.default_voice_id(),
        },
        "paths": {
            "health": "/health",
            "native_json": "/api/cosyvoice/tts",
            "native_upload": "/api/cosyvoice/tts/upload",
            "profiles": "/api/cosyvoice/profiles",
            "voices": "/api/cosyvoice/voices",
            "capabilities": "/api/cosyvoice/capabilities",
            "logs": "/api/cosyvoice/logs",
            "speakers": "/speakers",
            "openai_models": "/v1/models",
            "openai_voices": "/v1/audio/voices",
            "openai_speech": "/v1/audio/speech",
            "admin": admin_url,
        },
        "supports": {
            "native_json": True,
            "native_multipart": True,
            "prompt_audio_upload": True,
            "profile_lookup": True,
            "openai_compatible": True,
            "voice_sets": True,
            "model_presets": True,
            "sft": True,
        },
        "modes": [
            {
                "id": "prompt_clone",
                "engine_mode": "zero_shot",
                "label": MODE_LABELS["prompt_clone"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile", "prompt_text"],
            },
            {
                "id": "zero_shot",
                "engine_mode": "zero_shot",
                "label": MODE_LABELS["zero_shot"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile", "prompt_text"],
            },
            {
                "id": "cross_lingual",
                "engine_mode": "cross_lingual",
                "label": MODE_LABELS["cross_lingual"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile"],
            },
            {
                "id": "instruct",
                "engine_mode": "instruct",
                "label": MODE_LABELS["instruct"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile", "instruct_text"],
            },
            {
                "id": "sft",
                "label": MODE_LABELS["sft"],
                "required_fields": ["text", "sft_spk|profile"],
            },
        ],
        "aliases": MODE_ALIASES,
        "response_formats": sorted(CONTENT_TYPES),
        "model_presets": [preset.to_native_item() for preset in registry.list_model_presets()],
        "voice_sets": [voice_set.to_openai_model(len(registry.list_profiles(voice_set.id))) for voice_set in registry.list_voice_sets()],
        "profiles": _profile_items(registry),
    }


@router.get("/api/cosyvoice/logs", summary="Read CosyVoice3 runtime logs")
@router.get("/cosyvoice3/logs", include_in_schema=False)
def cosyvoice_logs(
    name: str = Query("backend.log", description="backend.log, backend.previous.log, admin-ui.out.log, admin-ui.err.log, download.out.log, download.err.log"),
    limit: int = Query(160, ge=1, le=1000),
):
    path = LOG_FILES.get(name)
    if path is None:
        return openai_error(f"Unknown log file: {name}", status_code=404, code="invalid_request")
    return {
        "object": "log",
        "name": name,
        "path": str(path),
        "newest_first": True,
        "content": read_log_file(path, limit=limit, newest_first=True),
    }


@router.get("/speakers", summary="List speakers (SillyTavern compatible)")
@router.get("/api/characters", include_in_schema=False)
def speakers(registry: VoiceRegistry = Depends(get_voice_registry)):
    return _speaker_items(registry)


@router.post("/api/cosyvoice/tts", summary="Generate speech with native CosyVoice JSON API")
@router.post("/api/cosyvoice/speech", include_in_schema=False)
@router.post("/cosyvoice/speech", include_in_schema=False)
def cosyvoice_speech(
    payload: CosyVoiceSpeechRequest,
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    try:
        synthesis_input = build_synthesis_input(payload, registry=registry, strict_profile=True)
        result = runtime.synthesize(synthesis_input)
        return audio_response(result, payload_response_format(payload))
    except FileNotFoundError as exc:
        return openai_error(str(exc), status_code=404, code="invalid_reference_audio")
    except ValueError as exc:
        message = str(exc)
        return openai_error(message, status_code=400, code=classify_error_code(message))
    except Exception as exc:
        return openai_error(str(exc), status_code=500, error_type="server_error", code="inference_failed")


@router.post("/api/cosyvoice/tts/upload", summary="Generate speech with uploaded prompt audio")
@router.post("/api/cosyvoice/speech/upload", include_in_schema=False)
@router.post("/cosyvoice/speech/upload", include_in_schema=False)
async def cosyvoice_speech_upload(
    text: str = Form(...),
    input: str | None = Form(None),
    mode: str | None = Form(None),
    profile: str | None = Form(None),
    character_name: str | None = Form(None),
    speaker: str | None = Form(None),
    voice: str | None = Form(None),
    prompt_audio_path: str | None = Form(None),
    reference_audio_path: str | None = Form(None),
    ref_audio_path: str | None = Form(None),
    prompt_audio: UploadFile | None = File(None),
    prompt_text: str | None = Form(None),
    reference_text: str | None = Form(None),
    instruct_text: str | None = Form(None),
    instruction_text: str | None = Form(None),
    instructions: str | None = Form(None),
    voice_instruction: str | None = Form(None),
    prompt_lang: str | None = Form(None),
    sft_spk: str | None = Form(None),
    spk_id: str | None = Form(None),
    speed: float = Form(1.0),
    response_format: str = Form("wav"),
    seed: int | None = Form(None),
    text_frontend: bool = Form(True),
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    temp_prompt_audio = ""
    try:
        temp_prompt_audio = await save_uploaded_audio(prompt_audio, prefix="prompt")
        payload = CosyVoiceSpeechRequest(
            text=text,
            input=input,
            mode=mode,
            profile=profile,
            character_name=character_name,
            speaker=speaker,
            voice=voice,
            prompt_audio_path=prompt_audio_path,
            reference_audio_path=reference_audio_path,
            ref_audio_path=ref_audio_path,
            prompt_text=prompt_text,
            reference_text=reference_text,
            instruct_text=instruct_text,
            instruction_text=instruction_text,
            instructions=instructions,
            voice_instruction=voice_instruction,
            prompt_lang=prompt_lang,
            sft_spk=sft_spk,
            spk_id=spk_id,
            speed=speed,
            response_format=response_format,
            seed=seed,
            text_frontend=text_frontend,
        )
        synthesis_input = build_synthesis_input(
            payload,
            registry=registry,
            uploaded_prompt_audio=temp_prompt_audio,
            strict_profile=False,
        )
        result = runtime.synthesize(synthesis_input)
        return audio_response(result, payload_response_format(payload))
    except FileNotFoundError as exc:
        return openai_error(str(exc), status_code=404, code="invalid_reference_audio")
    except ValueError as exc:
        message = str(exc)
        return openai_error(message, status_code=400, code=classify_error_code(message))
    except Exception as exc:
        return openai_error(str(exc), status_code=500, error_type="server_error", code="inference_failed")
    finally:
        cleanup_temp_file(temp_prompt_audio)


@router.post("/api/v1/tts/cosyvoice", include_in_schema=False)
@router.post("/api/tts/cosyvoice", include_in_schema=False)
@router.post("/api/tts", include_in_schema=False)
def legacy_native_speech(
    payload: CosyVoiceSpeechRequest,
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    return cosyvoice_speech(payload, runtime=runtime, registry=registry)
