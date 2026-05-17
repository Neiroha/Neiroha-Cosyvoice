from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any

from app.core.config import LOGS_ROOT

BACKEND_LOG_PATH = LOGS_ROOT / "backend.log"
BACKEND_PREVIOUS_LOG_PATH = LOGS_ROOT / "backend.previous.log"
ADMIN_STDOUT_LOG_PATH = LOGS_ROOT / "admin-ui.out.log"
ADMIN_STDERR_LOG_PATH = LOGS_ROOT / "admin-ui.err.log"
DOWNLOAD_STDOUT_LOG_PATH = LOGS_ROOT / "download.out.log"
DOWNLOAD_STDERR_LOG_PATH = LOGS_ROOT / "download.err.log"

LOG_FILES = {
    "backend.log": BACKEND_LOG_PATH,
    "backend.previous.log": BACKEND_PREVIOUS_LOG_PATH,
    "admin-ui.out.log": ADMIN_STDOUT_LOG_PATH,
    "admin-ui.err.log": ADMIN_STDERR_LOG_PATH,
    "download.out.log": DOWNLOAD_STDOUT_LOG_PATH,
    "download.err.log": DOWNLOAD_STDERR_LOG_PATH,
}


class RuntimeEventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()

    def reset_for_launch(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > 0:
                BACKEND_PREVIOUS_LOG_PATH.unlink(missing_ok=True)
                try:
                    self.path.replace(BACKEND_PREVIOUS_LOG_PATH)
                except OSError:
                    BACKEND_PREVIOUS_LOG_PATH.write_text(
                        self.path.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
            self.path.write_text("", encoding="utf-8")

    def append(self, event: str, **fields: Any) -> None:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = " ".join(
            f"{key}={self._format_value(value)}"
            for key, value in fields.items()
            if value is not None and self._format_value(value) != ""
        )
        line = f"{timestamp} | {event}"
        if details:
            line = f"{line} | {details}"
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")

    def tail(self, limit: int = 160, *, newest_first: bool = True) -> str:
        return read_log_file(self.path, limit=limit, newest_first=newest_first)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        if " " in text:
            return json.dumps(text, ensure_ascii=False)
        return text


def read_log_file(path: Path, *, limit: int = 160, newest_first: bool = True) -> str:
    if not path.exists():
        return f"No log file yet: {path}"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max(limit, 1) :]
    if newest_first:
        tail = list(reversed(tail))
    return "\n".join(tail) or f"No log entries yet: {path}"


def truncate_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


RUNTIME_EVENTS = RuntimeEventLog(BACKEND_LOG_PATH)
