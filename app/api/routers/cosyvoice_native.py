from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.common import (
    audio_response,
    build_synthesis_input,
    cleanup_temp_file,
    json_response,
    payload_response_format,
    save_uploaded_audio,
)
from app.api.dependencies import get_runtime, get_voice_registry
from app.core.profiles import MODE_ALIASES, MODE_LABELS, VoiceRegistry
from app.core.schemas import CosyVoiceSpeechRequest
from app.services.audio import CONTENT_TYPES
from app.services.cosyvoice_runtime import CosyVoiceRuntime

router = APIRouter(tags=["cosyvoice"])


def _profile_items(registry: VoiceRegistry) -> list[dict[str, object]]:
    return [profile.to_profile_item() for profile in registry.list_profiles()]


def _speaker_items(registry: VoiceRegistry) -> list[dict[str, object]]:
    return [profile.to_speaker_item() for profile in registry.list_profiles()]


@router.get("/cosyvoice/profiles", summary="List registered CosyVoice profiles")
def cosyvoice_profiles(registry: VoiceRegistry = Depends(get_voice_registry)):
    return {"object": "list", "data": _profile_items(registry)}


@router.get("/cosyvoice/meta", summary="Describe native CosyVoice capabilities")
def cosyvoice_meta(
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
):
    return {
        "provider": "cosyvoice",
        "model": runtime.model_id,
        "model_loaded": runtime.model_loaded,
        "paths": {
            "health": "/health",
            "native_json": "/cosyvoice/speech",
            "native_upload": "/cosyvoice/speech/upload",
            "profiles": "/cosyvoice/profiles",
            "speakers": "/speakers",
            "openai_models": "/v1/models",
            "openai_voices": "/v1/audio/voices",
            "openai_speech": "/v1/audio/speech",
            "gradio": "/gradio",
        },
        "supports": {
            "native_json": True,
            "native_multipart": True,
            "prompt_audio_upload": True,
            "profile_lookup": True,
            "openai_compatible": True,
            "sft": True,
        },
        "modes": [
            {
                "id": "zero_shot",
                "label": MODE_LABELS["zero_shot"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile", "prompt_text"],
            },
            {
                "id": "cross_lingual",
                "label": MODE_LABELS["cross_lingual"],
                "required_fields": ["text", "prompt_audio_path|prompt_audio|profile"],
            },
            {
                "id": "instruct",
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
        "profiles": _profile_items(registry),
    }


@router.get("/speakers", summary="List speakers (SillyTavern compatible)")
@router.get("/api/characters", include_in_schema=False)
def speakers(registry: VoiceRegistry = Depends(get_voice_registry)):
    return _speaker_items(registry)


@router.post("/cosyvoice/speech", summary="Generate speech with native CosyVoice JSON API")
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cosyvoice/speech/upload", summary="Generate speech with uploaded prompt audio")
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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

