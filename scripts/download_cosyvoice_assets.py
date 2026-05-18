from __future__ import annotations

import argparse
import os
import platform
import sys
import zipfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.core.config import (
    MODELS_ROOT,
    WETEXT_MODEL_DIR,
    ensure_ttsfrd_resource_link,
    patch_wetext_local_snapshot,
    prepare_runtime_environment,
)

MODEL_CATALOG = {
    "cosyvoice3": {
        "dir": "Fun-CosyVoice3-0.5B",
        "modelscope": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        "hf": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        "with_frontend": True,
    },
    "wetext": {
        "dir": "_cache/modelscope/models/pengzhendong/wetext",
        "modelscope": "pengzhendong/wetext",
        "hf": "pengzhendong/wetext",
    },
    "ttsfrd": {
        "dir": "CosyVoice-ttsfrd",
        "modelscope": "iic/CosyVoice-ttsfrd",
        "hf": "FunAudioLLM/CosyVoice-ttsfrd",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download CosyVoice model assets.")
    parser.add_argument("--model", choices=sorted(MODEL_CATALOG), default="cosyvoice3")
    parser.add_argument("--source", choices=["modelscope", "hf", "hf-mirror"], default="modelscope")
    parser.add_argument("--local-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="Accepted for Admin compatibility; existing files may be reused by the backend downloader.")
    parser.add_argument(
        "--frontend",
        choices=["auto", "wetext", "ttsfrd", "both", "none"],
        default="auto",
        help="Frontend resource to pre-download with CosyVoice3. auto downloads wetext on Windows and ttsfrd elsewhere.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Only download the requested model, without text frontend resources.",
    )
    parser.add_argument(
        "--skip-tokenizer",
        action="store_true",
        help="Deprecated alias for --skip-frontend.",
    )
    return parser.parse_args()


def download_modelscope(model_id: str, local_dir: Path) -> None:
    from modelscope import snapshot_download

    snapshot_download(model_id, local_dir=str(local_dir))


def download_hf(model_id: str, local_dir: Path, *, mirror: bool) -> None:
    if mirror:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=model_id, local_dir=str(local_dir))


def default_local_dir(model_key: str) -> Path:
    if model_key == "wetext":
        return WETEXT_MODEL_DIR
    return MODELS_ROOT / MODEL_CATALOG[model_key]["dir"]


def resolve_models_dir(model_key: str, local_dir: Path | None) -> Path:
    resolved = local_dir or default_local_dir(model_key)
    if not resolved.is_absolute():
        resolved = (WORKSPACE_ROOT / resolved).resolve()
    else:
        resolved = resolved.resolve()

    try:
        resolved.relative_to(MODELS_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Download destination must be under ./models, got: {resolved}") from exc
    return resolved


def unzip_ttsfrd_resource(local_dir: Path) -> None:
    resource_dir = local_dir / "resource"
    archive = local_dir / "resource.zip"
    if resource_dir.exists() or not archive.exists():
        return
    print(f"Extracting {archive} -> {local_dir}")
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(local_dir)


def warm_wetext_frontend() -> None:
    try:
        patch_wetext_local_snapshot()
        from wetext import Normalizer as EnNormalizer
        from wetext import Normalizer as ZhNormalizer

        ZhNormalizer(remove_erhua=False)
        EnNormalizer()
    except Exception as exc:
        raise RuntimeError(
            "Downloaded wetext resource, but failed to initialize wetext frontend."
        ) from exc


def frontend_resources(frontend: str, *, system_name: str | None = None) -> list[str]:
    if frontend == "none":
        return []
    if frontend == "both":
        return ["wetext", "ttsfrd"]
    if frontend in {"wetext", "ttsfrd"}:
        return [frontend]
    current_system = (system_name or platform.system()).lower()
    if current_system.startswith("win"):
        return ["wetext"]
    return ["ttsfrd"]


def download_one(model_key: str, source_arg: str, local_dir: Path | None = None) -> Path:
    entry = MODEL_CATALOG[model_key]
    if model_key == "wetext" and source_arg != "modelscope":
        print("wetext frontend is a ModelScope-backed resource; using modelscope cache.")
        source_arg = "modelscope"
    source = "hf" if source_arg == "hf-mirror" else source_arg
    model_id = entry[source]
    local_dir = resolve_models_dir(model_key, local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {model_id} -> {local_dir}")
    if source == "modelscope":
        download_modelscope(model_id, local_dir)
    else:
        download_hf(model_id, local_dir, mirror=source_arg == "hf-mirror")
    if model_key == "ttsfrd":
        unzip_ttsfrd_resource(local_dir)
        ensure_ttsfrd_resource_link()
    elif model_key == "wetext":
        warm_wetext_frontend()
    return local_dir


def main() -> None:
    prepare_runtime_environment()
    args = parse_args()
    if args.force:
        print("Force flag received; backend downloaders will refresh metadata and reuse valid local files.")
    download_one(args.model, args.source, args.local_dir)
    if MODEL_CATALOG[args.model].get("with_frontend") and not (args.skip_frontend or args.skip_tokenizer):
        for frontend in frontend_resources(args.frontend):
            download_one(frontend, args.source, None)
    print("Done.")


if __name__ == "__main__":
    main()
