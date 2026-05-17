from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.cosyvoice_native import router as cosyvoice_router
from app.api.routers.health import router as health_router
from app.api.routers.openai import router as openai_router
from app.core.profiles import VoiceRegistry
from app.services.cosyvoice_runtime import CosyVoiceRuntime

PUBLIC_PATH_PREFIXES = (
    "/health",
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
)


def create_api_app(
    runtime: CosyVoiceRuntime,
    voice_registry: VoiceRegistry,
    *,
    api_key: str = "",
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Neiroha CosyVoice Service",
        version="0.1.0",
        description="FastAPI wrapper around the official CosyVoice runtime with native and OpenAI-compatible routes.",
    )

    app.state.runtime = runtime
    app.state.voice_registry = voice_registry
    app.state.api_key = api_key

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def api_key_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        if not api_key or request.method == "OPTIONS":
            return await call_next(request)
        if any(request.url.path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        x_api_key = request.headers.get("x-api-key", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else x_api_key
        if supplied != api_key:
            return JSONResponse({"error": "Missing or invalid API key"}, status_code=401)
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(openai_router)
    app.include_router(cosyvoice_router)
    return app

