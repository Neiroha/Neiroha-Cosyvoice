from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_runtime, get_voice_registry
from app.core.profiles import VoiceRegistry
from app.services.cosyvoice_runtime import CosyVoiceRuntime

router = APIRouter(tags=["system"])


@router.get("/")
def root(request: Request, runtime: CosyVoiceRuntime = Depends(get_runtime)) -> dict[str, str | bool]:
    return {
        "message": "Neiroha CosyVoice service is running.",
        "model": runtime.model_id,
        "model_loaded": runtime.model_loaded,
        "api_url": getattr(request.app.state, "api_url", ""),
        "admin_url": getattr(request.app.state, "admin_url", ""),
    }


@router.get("/health")
@router.get("/api/health", include_in_schema=False)
def health(
    request: Request,
    runtime: CosyVoiceRuntime = Depends(get_runtime),
    registry: VoiceRegistry = Depends(get_voice_registry),
) -> dict[str, object]:
    return {
        "status": "ok",
        "backend": "cosyvoice3",
        "version": "0.1.0",
        "model": runtime.model_id,
        "loaded_model": runtime.model_id if runtime.model_loaded else "",
        "model_loaded": runtime.model_loaded,
        "sample_rate": runtime.sample_rate,
        "api_url": getattr(request.app.state, "api_url", ""),
        "admin_url": getattr(request.app.state, "admin_url", ""),
        "active_model_preset": registry.active_model_preset_id(),
        "active_voice_set": registry.active_voice_set_id(),
        "default_voice": registry.default_voice_id(),
        "voice_sets": [voice_set.id for voice_set in registry.list_voice_sets()],
        "profiles": [profile.id for profile in registry.list_profiles()],
        "authRequired": bool(getattr(request.app.state, "api_key", "")),
    }
