from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.api.main import create_api_app
from app.core.config import DEFAULT_MODEL_DIR, DEFAULT_PROFILE_PATH, DEFAULT_REPO_DIR, prepare_runtime_environment
from app.core.profiles import VoiceRegistry
from app.gradio_app import build_gradio_blocks
from app.services.cosyvoice_runtime import CosyVoiceRuntime

LOGGER = logging.getLogger("neiroha.cosyvoice")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch Neiroha CosyVoice with FastAPI, Gradio, or both.",
    )
    parser.add_argument("--mode", choices=["api", "webui", "combined"], default="combined")
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--gradio-path", default="/gradio")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--preload-model", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--load-trt", action="store_true")
    parser.add_argument("--load-vllm", action="store_true")
    parser.add_argument("--load-jit", action="store_true")
    parser.add_argument("--trt-concurrent", type=int, default=1)
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def resolve_port(mode: str, port: int | None) -> int:
    if port is not None:
        return port
    return 7860 if mode == "webui" else 9880


def main() -> None:
    configure_logging()
    prepare_runtime_environment()
    args = parse_args()
    port = resolve_port(args.mode, args.port)

    runtime = CosyVoiceRuntime(
        model_dir=args.model_dir,
        repo_dir=args.repo_dir,
        load_jit=args.load_jit,
        load_trt=args.load_trt,
        load_vllm=args.load_vllm,
        fp16=args.fp16,
        trt_concurrent=args.trt_concurrent,
    )
    registry = VoiceRegistry(args.profiles.resolve())

    if args.preload_model:
        runtime.get_or_load_model()

    LOGGER.info(
        "Starting Neiroha CosyVoice mode=%s repo=%s model=%s profiles=%s host=%s port=%s",
        args.mode,
        args.repo_dir,
        args.model_dir,
        args.profiles,
        args.host,
        port,
    )

    if args.mode == "webui":
        blocks = build_gradio_blocks(runtime, registry)
        blocks.launch(server_name=args.host, server_port=port, show_error=True)
        return

    api_app = create_api_app(runtime, registry, api_key=args.api_key)
    if args.mode == "api":
        uvicorn.run(api_app, host=args.host, port=port, log_level=args.log_level)
        return

    import gradio as gr

    mount_path = args.gradio_path if args.gradio_path.startswith("/") else f"/{args.gradio_path}"
    blocks = build_gradio_blocks(runtime, registry)
    app = gr.mount_gradio_app(api_app, blocks, path=mount_path, show_error=True)
    uvicorn.run(app, host=args.host, port=port, log_level=args.log_level)


if __name__ == "__main__":
    main()

