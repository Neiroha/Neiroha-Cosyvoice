from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

import uvicorn

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.api.main import create_api_app
from app.core.config import DEFAULT_PROFILE_PATH, DEFAULT_REPO_DIR, prepare_runtime_environment
from app.core.profiles import VoiceRegistry, first_non_empty, strip_text
from app.core.runtime_logs import (
    ADMIN_STDERR_LOG_PATH,
    ADMIN_STDOUT_LOG_PATH,
    RUNTIME_EVENTS,
    truncate_log,
)
from app.admin.gradio_app import build_gradio_admin_blocks
from app.services.cosyvoice_runtime import CosyVoiceRuntime

LOGGER = logging.getLogger("neiroha.cosyvoice")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch Neiroha CosyVoice3 FastAPI and Gradio Admin.",
    )
    parser.add_argument(
        "--mode",
        choices=[
            "api",
            "admin",
            "api-admin",
            "serve",
        ],
        default=None,
        help="Compatibility alias for --surface. Omit it to use [startup].surface from configs/server.toml.",
    )
    parser.add_argument(
        "--surface",
        choices=["api", "admin", "both"],
        default=None,
        help="Override only the startup surface from configs/server.toml.",
    )
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--api-host", default=None)
    parser.add_argument("--api-port", type=int, default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--admin-host", default=None)
    parser.add_argument("--admin-port", type=int, default=None)
    parser.add_argument("--model-preset", default="")
    parser.add_argument("--api-key", default=os.environ.get("NEIROHA_COSYVOICE3_API_KEY", ""))
    parser.add_argument("--preload-model", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--load-trt", action="store_true")
    parser.add_argument("--load-vllm", action="store_true")
    parser.add_argument("--load-jit", action="store_true")
    parser.add_argument("--trt-concurrent", type=int, default=0)
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


def surface_to_mode(surface: object) -> str:
    normalized = strip_text(surface).lower().replace("_", "-")
    if normalized == "api":
        return "api"
    if normalized == "admin":
        return "admin"
    if normalized in {"both", "api-admin", "combined", "serve"}:
        return "api-admin"
    return "api-admin"


def mode_settings(
    *,
    mode: str | None,
    surface: str | None,
    startup_config: dict[str, object],
    preload_model: bool,
) -> tuple[str, bool]:
    configured_mode = surface_to_mode(surface or startup_config.get("surface", "both"))
    if mode in {None, "", "serve"}:
        return configured_mode, preload_model
    return surface_to_mode(mode), preload_model


def socket_bind_host(host: str) -> str:
    return strip_text(host) or "127.0.0.1"


def browser_host(host: str) -> str:
    host = socket_bind_host(host)
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def http_url(host: str, port: int) -> str:
    return f"http://{browser_host(host)}:{int(port)}"


def _socket_family(host: str) -> socket.AddressFamily:
    return socket.AF_INET6 if ":" in socket_bind_host(host) else socket.AF_INET


def can_bind_port(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.socket(_socket_family(host), socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((socket_bind_host(host), int(port)))
        return True, ""
    except OSError as exc:
        return False, str(exc)


def random_bindable_port(host: str) -> int:
    with socket.socket(_socket_family(host), socket.SOCK_STREAM) as sock:
        sock.bind((socket_bind_host(host), 0))
        return int(sock.getsockname()[1])


def resolve_bind_port(host: str, requested_port: int, label: str) -> int:
    requested_port = int(requested_port)
    ok, reason = can_bind_port(host, requested_port)
    if ok:
        return requested_port
    selected_port = random_bindable_port(host)
    LOGGER.warning(
        "%s configured port %s is unavailable on %s; using %s. Reason: %s",
        label,
        requested_port,
        socket_bind_host(host),
        selected_port,
        reason,
    )
    RUNTIME_EVENTS.append(
        "port_fallback",
        service=label,
        host=socket_bind_host(host),
        requested_port=requested_port,
        selected_port=selected_port,
        reason=reason,
    )
    return selected_port


def local_api_base(api_url: str, api_port: int) -> str:
    parsed = urllib.parse.urlparse(api_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"{scheme}://{host}:{api_port}"


class ManagedAdminProcess:
    def __init__(self, *, host: str, port: int, api_base: str, log_level: str) -> None:
        self.host = host
        self.port = port
        self.api_base = api_base
        self.log_level = log_level
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> str:
        truncate_log(ADMIN_STDOUT_LOG_PATH)
        truncate_log(ADMIN_STDERR_LOG_PATH)
        env = os.environ.copy()
        env["NEIROHA_COSYVOICE3_API_BASE"] = self.api_base
        env["NEIROHA_COSYVOICE3_ADMIN_URL"] = http_url(self.host, self.port)
        command = [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "launch_cosyvoice.py"),
            "--mode",
            "admin",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--api-base",
            self.api_base,
            "--log-level",
            self.log_level,
        ]
        stdout = ADMIN_STDOUT_LOG_PATH.open("w", encoding="utf-8", errors="replace")
        stderr = ADMIN_STDERR_LOG_PATH.open("w", encoding="utf-8", errors="replace")
        self.process = subprocess.Popen(
            command,
            cwd=WORKSPACE_ROOT,
            env=env,
            text=True,
            stdout=stdout,
            stderr=stderr,
        )
        return f"started Gradio Admin pid={self.process.pid}"

    def stop(self) -> str:
        if self.process is None:
            return "admin process was not started"
        if self.process.poll() is None:
            self.process.terminate()
            return f"terminated Gradio Admin pid={self.process.pid}"
        return f"Gradio Admin already exited code={self.process.returncode}"


def _config_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def main() -> None:
    configure_logging()
    prepare_runtime_environment()
    args = parse_args()
    registry = VoiceRegistry(args.profiles.resolve())
    server_config = registry.server_config()
    api_config = server_config.get("api", {}) if isinstance(server_config.get("api"), dict) else {}
    admin_config = server_config.get("admin", {}) if isinstance(server_config.get("admin"), dict) else {}
    startup_config = server_config.get("startup", {}) if isinstance(server_config.get("startup"), dict) else {}
    security_config = server_config.get("security", {}) if isinstance(server_config.get("security"), dict) else {}
    config_preload = _config_bool(
        startup_config.get("preload_model", api_config.get("preload_model")),
        False,
    )
    effective_mode, preload_model = mode_settings(
        mode=args.mode,
        surface=args.surface,
        startup_config=startup_config,
        preload_model=args.preload_model or config_preload,
    )

    if effective_mode != "admin":
        RUNTIME_EVENTS.reset_for_launch()

    starts_api = effective_mode in {"api", "api-admin"}
    starts_admin = effective_mode in {"admin", "api-admin"}
    api_host = first_non_empty(
        args.api_host,
        args.host if effective_mode == "api" else "",
        api_config.get("host"),
        "127.0.0.1",
    )
    admin_host = first_non_empty(
        args.admin_host,
        args.host if effective_mode == "admin" else "",
        admin_config.get("host"),
        "127.0.0.1",
    )
    requested_api_port = int(args.api_port or (args.port if effective_mode == "api" else 0) or api_config.get("port") or 19890)
    requested_admin_port = int(args.admin_port or (args.port if effective_mode == "admin" else 0) or admin_config.get("port") or 17870)
    api_port = resolve_bind_port(api_host, requested_api_port, "FastAPI") if starts_api else requested_api_port
    admin_port = resolve_bind_port(admin_host, requested_admin_port, "Gradio Admin") if starts_admin else requested_admin_port
    api_url = args.api_base or http_url(api_host, api_port)
    admin_url = http_url(admin_host, admin_port) if starts_admin else ""

    if effective_mode == "admin":
        LOGGER.info("Gradio Admin URL: %s", admin_url)
        LOGGER.info("Admin connects to FastAPI: %s", api_url)
        blocks = build_gradio_admin_blocks(api_base=api_url, admin_url=admin_url, registry=registry)
        blocks.launch(
            server_name=admin_host,
            server_port=admin_port,
            share=_config_bool(admin_config.get("share"), False),
            show_error=True,
        )
        return

    preset_id = first_non_empty(args.model_preset, startup_config.get("default_model_preset"), registry.active_model_preset_id())
    preset = registry.get_model_preset(preset_id)
    runtime = CosyVoiceRuntime(
        model_dir=preset.model_dir,
        repo_dir=args.repo_dir,
        load_jit=args.load_jit or preset.load_jit,
        load_trt=args.load_trt or preset.load_trt,
        load_vllm=args.load_vllm or preset.load_vllm,
        fp16=args.fp16 or preset.fp16,
        trt_concurrent=args.trt_concurrent or preset.trt_concurrent,
    )

    if preload_model:
        runtime.get_or_load_model()

    ui_api_base = local_api_base(api_url, api_port)
    admin_process: ManagedAdminProcess | None = None
    if effective_mode == "api-admin":
        admin_process = ManagedAdminProcess(
            host=admin_host,
            port=admin_port,
            api_base=ui_api_base,
            log_level=args.log_level,
        )
        LOGGER.info(admin_process.start())

    RUNTIME_EVENTS.append(
        "launcher_start",
        mode=effective_mode,
        requested_mode=args.mode,
        api_url=http_url(api_host, api_port),
        admin_url=admin_url,
        model_preset=preset.id,
        model_dir=preset.model_dir,
        voice_set=registry.active_voice_set_id(),
        default_voice=registry.default_voice_id(),
        preload_model=preload_model,
    )
    LOGGER.info("FastAPI URL: %s", http_url(api_host, api_port))
    if admin_url:
        LOGGER.info("Gradio Admin URL: %s", admin_url)

    app = create_api_app(
        runtime,
        registry,
        api_key=first_non_empty(args.api_key, security_config.get("api_key")),
        api_url=http_url(api_host, api_port),
        admin_url=admin_url,
    )
    try:
        uvicorn.run(app, host=api_host, port=api_port, log_level=args.log_level)
    finally:
        if admin_process is not None:
            RUNTIME_EVENTS.append("admin_child_stop", message=admin_process.stop())


if __name__ == "__main__":
    main()
