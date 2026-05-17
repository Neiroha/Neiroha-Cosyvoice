from __future__ import annotations

from fastapi import Request

from app.core.profiles import VoiceRegistry
from app.services.cosyvoice_runtime import CosyVoiceRuntime


def get_runtime(request: Request) -> CosyVoiceRuntime:
    return request.app.state.runtime


def get_voice_registry(request: Request) -> VoiceRegistry:
    return request.app.state.voice_registry

