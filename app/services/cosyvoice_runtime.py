from __future__ import annotations

import logging
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import DEFAULT_REPO_DIR, WORKSPACE_ROOT, patch_wetext_local_snapshot, prepare_runtime_environment
from app.core.profiles import mode_label, normalize_mode_name, strip_text
from app.services.audio import audio_duration_seconds

LOGGER = logging.getLogger("neiroha.cosyvoice")


@dataclass(frozen=True)
class SynthesisInput:
    text: str
    mode: str
    prompt_audio: str = ""
    prompt_text: str = ""
    instruct_text: str = ""
    sft_spk: str = ""
    speed: float = 1.0
    seed: int | None = None
    text_frontend: bool = True
    voice_name: str = ""


@dataclass(frozen=True)
class SynthesisResult:
    sample_rate: int
    audio: Any
    elapsed_seconds: float
    audio_seconds: float
    rtf: float
    mode: str
    voice_name: str


def _patch_ruamel_loader_compat() -> None:
    try:
        import ruamel.yaml
    except ImportError:
        return

    for loader_name in ("Loader", "SafeLoader", "RoundTripLoader", "FullLoader"):
        loader_cls = getattr(ruamel.yaml, loader_name, None)
        if loader_cls is not None and not hasattr(loader_cls, "max_depth"):
            loader_cls.max_depth = None


class CosyVoiceRuntime:
    def __init__(
        self,
        *,
        model_dir: str | Path,
        repo_dir: str | Path = DEFAULT_REPO_DIR,
        load_jit: bool = False,
        load_trt: bool = False,
        load_vllm: bool = False,
        fp16: bool = False,
        trt_concurrent: int = 1,
    ) -> None:
        self.model_dir = self._resolve_model_dir(model_dir)
        self.repo_dir = Path(repo_dir).resolve()
        self.load_jit = load_jit
        self.load_trt = load_trt
        self.load_vllm = load_vllm
        self.fp16 = fp16
        self.trt_concurrent = trt_concurrent
        self.model = None
        self.lock = threading.RLock()
        self._imports_ready = False

    @staticmethod
    def _resolve_model_dir(model_dir: str | Path) -> Path:
        candidate = Path(model_dir).expanduser()
        if candidate.is_absolute():
            return candidate
        return (WORKSPACE_ROOT / candidate).resolve()

    @property
    def model_id(self) -> str:
        return str(self.model_dir)

    @property
    def model_loaded(self) -> bool:
        return self.model is not None

    @property
    def sample_rate(self) -> int:
        if self.model is None:
            return 0
        return int(getattr(self.model, "sample_rate", 0) or 0)

    def prepare_imports(self) -> None:
        if self._imports_ready:
            return
        prepare_runtime_environment()
        if not self.repo_dir.exists():
            raise FileNotFoundError(f"CosyVoice repo directory does not exist: {self.repo_dir}")
        matcha_path = self.repo_dir / "third_party" / "Matcha-TTS"
        for path in (self.repo_dir, matcha_path):
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))
        os.environ.setdefault("TQDM_DISABLE", "1")
        patch_wetext_local_snapshot()
        _patch_ruamel_loader_compat()
        self._imports_ready = True

    def _load_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model_dir": str(self.model_dir),
            "fp16": self.fp16,
        }
        if (self.model_dir / "cosyvoice3.yaml").exists():
            kwargs.update(
                load_trt=self.load_trt,
                load_vllm=self.load_vllm,
                trt_concurrent=self.trt_concurrent,
            )
        elif (self.model_dir / "cosyvoice2.yaml").exists():
            kwargs.update(
                load_jit=self.load_jit,
                load_trt=self.load_trt,
                load_vllm=self.load_vllm,
                trt_concurrent=self.trt_concurrent,
            )
        elif (self.model_dir / "cosyvoice.yaml").exists():
            kwargs.update(
                load_jit=self.load_jit,
                load_trt=self.load_trt,
                trt_concurrent=self.trt_concurrent,
            )
        return kwargs

    def get_or_load_model(self):
        with self.lock:
            if self.model is not None:
                return self.model
            self.prepare_imports()
            from cosyvoice.cli.cosyvoice import AutoModel

            LOGGER.info("Loading CosyVoice model from %s", self.model_dir)
            self.model = AutoModel(**self._load_kwargs())
            LOGGER.info("CosyVoice model loaded: %s", self.model.__class__.__name__)
            return self.model

    def unload(self) -> None:
        with self.lock:
            model = self.model
            self.model = None
        if model is None:
            return
        del model
        try:
            import gc
            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            LOGGER.debug("Failed to clear CUDA cache", exc_info=True)

    def list_sft_speakers(self) -> list[str]:
        model = self.get_or_load_model()
        if not hasattr(model, "list_available_spks"):
            return []
        try:
            return list(model.list_available_spks())
        except Exception:
            LOGGER.debug("Failed to list SFT speakers", exc_info=True)
            return []

    def _set_seed(self, seed: int | None) -> None:
        if seed is None:
            return
        self.prepare_imports()
        try:
            from cosyvoice.utils.common import set_all_random_seed

            set_all_random_seed(int(seed))
            return
        except Exception:
            pass
        random.seed(int(seed))
        try:
            import torch

            torch.manual_seed(int(seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(seed))
        except Exception:
            LOGGER.debug("Failed to set torch seed", exc_info=True)

    @staticmethod
    def _is_cosyvoice3(model: Any) -> bool:
        return model.__class__.__name__ == "CosyVoice3" or "CosyVoice3" in getattr(model, "model_dir", "")

    @staticmethod
    def _format_cosyvoice3_prompt(prompt_text: str) -> str:
        if "<|endofprompt|>" in prompt_text:
            return prompt_text
        return f"You are a helpful assistant.<|endofprompt|>{prompt_text}"

    @staticmethod
    def _format_cosyvoice3_instruct(instruct_text: str) -> str:
        text = instruct_text
        if "<|endofprompt|>" not in text:
            text = f"{text}<|endofprompt|>"
        if "You are a helpful assistant." not in text:
            text = f"You are a helpful assistant. {text}"
        return text

    def synthesize(self, request: SynthesisInput) -> SynthesisResult:
        mode = normalize_mode_name(request.mode)
        if not mode:
            raise ValueError("mode is required.")

        model = self.get_or_load_model()
        self._set_seed(request.seed)
        is_v3 = self._is_cosyvoice3(model)
        started_at = time.perf_counter()

        LOGGER.info(
            "Synthesizing mode=%s voice=%s text_len=%s speed=%s",
            mode_label(mode),
            request.voice_name or request.sft_spk or "ad-hoc",
            len(request.text),
            request.speed,
        )

        outputs: list[Any] = []
        stream = False
        speed = float(request.speed or 1.0)
        text_frontend = bool(request.text_frontend)

        with self.lock:
            if mode == "zero_shot":
                if not request.prompt_audio:
                    raise ValueError("zero_shot requires prompt_audio_path or uploaded prompt_audio.")
                if not request.prompt_text:
                    raise ValueError("zero_shot requires prompt_text.")
                prompt_text = (
                    self._format_cosyvoice3_prompt(request.prompt_text)
                    if is_v3
                    else request.prompt_text
                )
                iterator = model.inference_zero_shot(
                    request.text,
                    prompt_text,
                    request.prompt_audio,
                    stream=stream,
                    speed=speed,
                    text_frontend=text_frontend,
                )
            elif mode == "cross_lingual":
                if not request.prompt_audio:
                    raise ValueError("cross_lingual requires prompt_audio_path or uploaded prompt_audio.")
                text = self._format_cosyvoice3_prompt(request.text) if is_v3 else request.text
                iterator = model.inference_cross_lingual(
                    text,
                    request.prompt_audio,
                    stream=stream,
                    speed=speed,
                    text_frontend=text_frontend,
                )
            elif mode == "instruct":
                if not request.instruct_text:
                    raise ValueError("instruct requires instruct_text.")
                instruct_text = (
                    self._format_cosyvoice3_instruct(request.instruct_text)
                    if is_v3
                    else request.instruct_text
                )
                if hasattr(model, "inference_instruct2"):
                    if not request.prompt_audio:
                        raise ValueError("instruct requires prompt_audio_path or uploaded prompt_audio.")
                    iterator = model.inference_instruct2(
                        request.text,
                        instruct_text,
                        request.prompt_audio,
                        stream=stream,
                        speed=speed,
                        text_frontend=text_frontend,
                    )
                else:
                    if not request.sft_spk:
                        raise ValueError("CosyVoice instruct models require sft_spk.")
                    iterator = model.inference_instruct(
                        request.text,
                        request.sft_spk,
                        instruct_text,
                        stream=stream,
                        speed=speed,
                        text_frontend=text_frontend,
                    )
            elif mode == "sft":
                sft_spk = request.sft_spk
                if not sft_spk:
                    speakers = self.list_sft_speakers()
                    if len(speakers) == 1:
                        sft_spk = speakers[0]
                if not sft_spk:
                    raise ValueError("sft mode requires sft_spk.")
                iterator = model.inference_sft(
                    request.text,
                    sft_spk,
                    stream=stream,
                    speed=speed,
                    text_frontend=text_frontend,
                )
            else:
                raise ValueError(f"Unsupported mode: {mode}")

            for item in iterator:
                if "tts_speech" in item:
                    outputs.append(item["tts_speech"])

        if not outputs:
            raise RuntimeError("CosyVoice returned no audio.")

        import torch

        audio = torch.concat(outputs, dim=1)
        elapsed = time.perf_counter() - started_at
        sample_rate = int(getattr(model, "sample_rate", 22050) or 22050)
        audio_seconds = audio_duration_seconds(audio, sample_rate)
        rtf = elapsed / audio_seconds if audio_seconds > 0 else 0.0
        LOGGER.info(
            "Synthesis completed | synth_seconds=%.2fs | audio_seconds=%.2fs | RTF=%.4f",
            elapsed,
            audio_seconds,
            rtf,
        )
        return SynthesisResult(
            sample_rate=sample_rate,
            audio=audio,
            elapsed_seconds=elapsed,
            audio_seconds=audio_seconds,
            rtf=rtf,
            mode=mode,
            voice_name=strip_text(request.voice_name),
        )
