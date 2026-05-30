from __future__ import annotations

import os
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_DIR = WORKSPACE_ROOT / "CosyVoice"
CONFIG_ROOT = WORKSPACE_ROOT / "configs"
SERVER_CONFIG_PATH = CONFIG_ROOT / "server.toml"
MODEL_PRESETS_DIR = CONFIG_ROOT / "model-presets"
VOICE_SETS_DIR = CONFIG_ROOT / "voice-sets"
MODELS_ROOT = WORKSPACE_ROOT / "models"
CACHE_ROOT = MODELS_ROOT / "_cache"
RUNTIME_ROOT = WORKSPACE_ROOT / "runtime"
RUNTIME_CACHE_ROOT = RUNTIME_ROOT / "cache"
RUNTIME_VOICES_ROOT = RUNTIME_ROOT / "voices"
TEMP_ROOT = RUNTIME_ROOT / "temp"
UPLOAD_ROOT = TEMP_ROOT / "uploads"
OUTPUT_ROOT = RUNTIME_ROOT / "outputs"
LOGS_ROOT = RUNTIME_ROOT / "logs"
MODELSCOPE_CACHE_ROOT = CACHE_ROOT / "modelscope"
HUGGINGFACE_CACHE_ROOT = CACHE_ROOT / "huggingface"
TORCH_CACHE_ROOT = CACHE_ROOT / "torch"
TTSFRD_MODEL_DIR = MODELS_ROOT / "CosyVoice-ttsfrd"
OFFICIAL_TTSFRD_MODEL_DIR = DEFAULT_REPO_DIR / "pretrained_models" / "CosyVoice-ttsfrd"
WETEXT_MODEL_DIR = MODELSCOPE_CACHE_ROOT / "models" / "pengzhendong" / "wetext"
DEFAULT_MODEL_DIR = MODELS_ROOT / "Fun-CosyVoice3-0.5B"
DEFAULT_PROFILE_PATH = WORKSPACE_ROOT / "profiles" / "voices.json"
DEFAULT_MODEL_PRESET_ID = "cosyvoice3-default"
DEFAULT_VOICE_SET_ID = "default"
DEFAULT_VOICE_ID = "prompt-clone"
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 9880
DEFAULT_ADMIN_HOST = "127.0.0.1"
DEFAULT_ADMIN_PORT = 7880


def prepare_runtime_environment() -> None:
    for path in (
        MODELS_ROOT,
        CACHE_ROOT,
        RUNTIME_ROOT,
        RUNTIME_CACHE_ROOT,
        RUNTIME_VOICES_ROOT,
        TEMP_ROOT,
        UPLOAD_ROOT,
        OUTPUT_ROOT,
        LOGS_ROOT,
        MODELSCOPE_CACHE_ROOT,
        HUGGINGFACE_CACHE_ROOT,
        TORCH_CACHE_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["TMPDIR"] = str(TEMP_ROOT)
    os.environ["TEMP"] = str(TEMP_ROOT)
    os.environ["TMP"] = str(TEMP_ROOT)
    os.environ["GRADIO_TEMP_DIR"] = str(TEMP_ROOT / "gradio")
    os.environ["MODELSCOPE_CACHE"] = str(MODELSCOPE_CACHE_ROOT)
    os.environ["MODELSCOPE_MODULES_CACHE"] = str(MODELSCOPE_CACHE_ROOT / "modules")
    os.environ["HF_HOME"] = str(HUGGINGFACE_CACHE_ROOT)
    os.environ["HF_HUB_CACHE"] = str(HUGGINGFACE_CACHE_ROOT / "hub")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(HUGGINGFACE_CACHE_ROOT / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(HUGGINGFACE_CACHE_ROOT / "transformers")
    os.environ["XDG_CACHE_HOME"] = str(CACHE_ROOT / "xdg")
    os.environ["TORCH_HOME"] = str(TORCH_CACHE_ROOT)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TQDM_DISABLE", "1")
    ensure_ttsfrd_resource_link()
    patch_wetext_local_snapshot()


def ensure_ttsfrd_resource_link() -> None:
    if not TTSFRD_MODEL_DIR.exists() or OFFICIAL_TTSFRD_MODEL_DIR.exists():
        return

    OFFICIAL_TTSFRD_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(TTSFRD_MODEL_DIR, OFFICIAL_TTSFRD_MODEL_DIR, target_is_directory=True)
        return
    except OSError:
        pass

    try:
        subprocess.run(
            [
                "cmd",
                "/c",
                "mklink",
                "/J",
                str(OFFICIAL_TTSFRD_MODEL_DIR),
                str(TTSFRD_MODEL_DIR),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        pass


def patch_wetext_local_snapshot() -> bool:
    if not WETEXT_MODEL_DIR.exists():
        return False

    try:
        import wetext.wetext as wetext_module
    except ImportError:
        return False

    def local_snapshot_download(model_id: str, *args, **kwargs) -> str:
        if model_id == "pengzhendong/wetext":
            return str(WETEXT_MODEL_DIR)
        from modelscope import snapshot_download

        return snapshot_download(model_id, *args, **kwargs)

    wetext_module.snapshot_download = local_snapshot_download
    return True


prepare_runtime_environment()
