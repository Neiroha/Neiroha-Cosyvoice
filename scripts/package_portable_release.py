from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = WORKSPACE_ROOT / ".codex-temp" / "portable"
DEFAULT_PACKAGE_NAME = "neiroha-cosyvoice3-portable"
WINDOWS_OPTIONAL_MODEL_DIRS = {"CosyVoice-ttsfrd"}

ROOT_FILES = [
    "start_portable.bat",
    "pixi.toml",
    "pixi.lock",
    "README.md",
    "README_zh.md",
]

TREE_SPECS = [
    (".pixi/envs/default", ".pixi/envs/default"),
    ("app", "app"),
    ("scripts", "scripts"),
    ("CosyVoice", "CosyVoice"),
    ("configs", "configs"),
    ("docs", "docs"),
    ("models", "models"),
    ("profiles", "profiles"),
]

EXCLUDED_DIRS = {
    ".github",
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "._____temp",
    "task-cache-v0",
}

EXCLUDED_FILES = {
    ".git",
    ".gitmodules",
    "*.pyc",
    "*.pyo",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Windows portable Neiroha CosyVoice3 package.")
    parser.add_argument("--name", default=DEFAULT_PACKAGE_NAME, help="Top-level package directory and archive name.")
    parser.add_argument("--stage-only", action="store_true", help="Only create the staged portable directory.")
    parser.add_argument("--skip-extract", action="store_true", help="Create and test the archive without extracting it.")
    parser.add_argument("--volume-size", default="2000MB", help="Bandizip split volume size. Keep at or below 2000MB for GitHub upload workflows.")
    parser.add_argument("--compression-level", default="5", help="Bandizip compression level. 5 balances size and build time for release packages.")
    parser.add_argument("--include-ttsfrd", action="store_true", help="Include optional CosyVoice ttsfrd assets. Windows portable packages omit them by default.")
    parser.add_argument("--bz", default="", help="Path to bz.exe. Defaults to PATH lookup.")
    return parser.parse_args()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_rmtree(path: Path) -> None:
    resolved = path.resolve()
    build_root = BUILD_ROOT.resolve()
    if not is_relative_to(resolved, build_root):
        raise RuntimeError(f"Refusing to remove path outside build root: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, check=True)


def robocopy(
    source: Path,
    target: Path,
    *,
    exclude_pretrained_models: bool = False,
    extra_excluded_dirs: set[str] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    excluded_dirs = set(EXCLUDED_DIRS)
    if exclude_pretrained_models:
        excluded_dirs.add("pretrained_models")
    if extra_excluded_dirs:
        excluded_dirs.update(extra_excluded_dirs)
    command = [
        "robocopy",
        str(source),
        str(target),
        "/MIR",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NP",
        "/XD",
        *sorted(excluded_dirs),
        "/XF",
        *sorted(EXCLUDED_FILES),
    ]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, text=True)
    if result.returncode > 7:
        raise subprocess.CalledProcessError(result.returncode, command)


def copy_runtime(stage_root: Path) -> None:
    runtime_root = stage_root / "runtime"
    for relative in ["cache", "logs", "outputs", "temp", "temp/gradio", "temp/uploads", "voices"]:
        (runtime_root / relative).mkdir(parents=True, exist_ok=True)
    gitkeep = WORKSPACE_ROOT / "runtime" / ".gitkeep"
    if gitkeep.exists():
        shutil.copy2(gitkeep, runtime_root / ".gitkeep")
    voices_source = WORKSPACE_ROOT / "runtime" / "voices"
    if voices_source.exists():
        robocopy(voices_source, runtime_root / "voices")
    for relative in ["cache/.gitkeep", "logs/.gitkeep", "outputs/.gitkeep"]:
        source = WORKSPACE_ROOT / "runtime" / relative
        if source.exists():
            target = runtime_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def copy_root_files(stage_root: Path) -> None:
    for relative in ROOT_FILES:
        source = WORKSPACE_ROOT / relative
        if source.exists():
            target = stage_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=WORKSPACE_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def write_manifest(stage_root: Path) -> None:
    payload = {
        "name": stage_root.name,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(WORKSPACE_ROOT),
        "git_commit": git_commit(),
        "default_api": "http://127.0.0.1:9880",
        "default_admin": "http://127.0.0.1:7880",
        "launcher": "start_portable.bat",
        "notes": [
            "Run from the unpacked directory.",
            "Uses bundled .pixi/envs/default/python.exe directly.",
            "Runtime logs, outputs, temp files, and caches remain under runtime/ and models/_cache/.",
        ],
    }
    (stage_root / ".portable-manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def stage_package(name: str, *, include_ttsfrd: bool = False) -> Path:
    stage_root = BUILD_ROOT / "stage" / name
    safe_rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    for source_relative, target_relative in TREE_SPECS:
        source = WORKSPACE_ROOT / source_relative
        if not source.exists():
            continue
        target = stage_root / target_relative
        extra_excluded_dirs = set()
        if source_relative == "models" and not include_ttsfrd:
            extra_excluded_dirs.update(WINDOWS_OPTIONAL_MODEL_DIRS)
        robocopy(
            source,
            target,
            exclude_pretrained_models=source_relative == "CosyVoice",
            extra_excluded_dirs=extra_excluded_dirs,
        )

    copy_runtime(stage_root)
    copy_root_files(stage_root)
    write_manifest(stage_root)
    return stage_root


def find_bz(explicit: str) -> str:
    if explicit:
        return explicit
    found = shutil.which("bz.exe") or shutil.which("bz")
    if found:
        return found
    common_paths = [
        Path("D:/Programs/Bandizip/Bandizip/bz.exe"),
        Path("C:/Program Files/Bandizip/bz.exe"),
        Path("C:/Program Files (x86)/Bandizip/bz.exe"),
    ]
    for path in common_paths:
        if path.exists():
            return str(path)
    raise RuntimeError("bz.exe was not found. Install Bandizip or pass --bz.")


def first_archive_part(archive_root: Path, name: str) -> Path:
    first_split = archive_root / f"{name}.7z.001"
    if first_split.exists():
        return first_split
    plain = archive_root / f"{name}.7z"
    if plain.exists():
        return plain
    raise RuntimeError(f"Archive was not created under {archive_root}")


def prepare_archive_root() -> Path:
    archive_root = BUILD_ROOT / "archive"
    try:
        safe_rmtree(archive_root)
        archive_root.mkdir(parents=True, exist_ok=True)
        return archive_root
    except PermissionError as exc:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fallback_root = BUILD_ROOT / f"archive-{timestamp}"
        print(f"warning=archive_root_locked path={archive_root} error={exc}")
        safe_rmtree(fallback_root)
        fallback_root.mkdir(parents=True, exist_ok=True)
        return fallback_root


def build_archive(stage_root: Path, *, bz: str, volume_size: str, compression_level: str) -> Path:
    archive_root = prepare_archive_root()
    archive_path = archive_root / f"{stage_root.name}.7z"
    run(
        [
            bz,
            "c",
            f"-fmt:7z",
            f"-v:{volume_size}",
            f"-l:{compression_level}",
            str(archive_path),
            stage_root.name,
        ],
        cwd=stage_root.parent,
    )
    first_part = first_archive_part(archive_root, stage_root.name)
    run([bz, "t", str(first_part)])
    return first_part


def extract_archive(first_part: Path, *, bz: str) -> Path:
    extracted_root = BUILD_ROOT / "extracted"
    safe_rmtree(extracted_root)
    extracted_root.mkdir(parents=True, exist_ok=True)
    run([bz, "x", "-aoa", f"-o:{extracted_root}", str(first_part)])
    return extracted_root


def dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        root_path = Path(root)
        for file_name in files:
            try:
                total += (root_path / file_name).stat().st_size
            except OSError:
                pass
    return total


def main() -> None:
    args = parse_args()
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    stage_root = stage_package(args.name, include_ttsfrd=args.include_ttsfrd)
    print(f"staged={stage_root}")
    print(f"staged_bytes={dir_size(stage_root)}")

    if args.stage_only:
        return

    bz = find_bz(args.bz)
    first_part = build_archive(
        stage_root,
        bz=bz,
        volume_size=args.volume_size,
        compression_level=args.compression_level,
    )
    print(f"archive_first_part={first_part}")

    if not args.skip_extract:
        extracted_root = extract_archive(first_part, bz=bz)
        print(f"extracted={extracted_root}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
