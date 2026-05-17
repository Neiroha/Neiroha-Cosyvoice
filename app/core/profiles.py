from __future__ import annotations

import json
import shutil
import tomllib
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.core.config import (
    CONFIG_ROOT,
    DEFAULT_MODEL_DIR,
    DEFAULT_MODEL_PRESET_ID,
    DEFAULT_PROFILE_PATH,
    DEFAULT_REPO_DIR,
    DEFAULT_VOICE_ID,
    DEFAULT_VOICE_SET_ID,
    MODEL_PRESETS_DIR,
    RUNTIME_VOICES_ROOT,
    SERVER_CONFIG_PATH,
    VOICE_SETS_DIR,
    WORKSPACE_ROOT,
)

MODE_LABELS = {
    "prompt_clone": "语音克隆",
    "zero_shot": "语音克隆",
    "cross_lingual": "跨语种克隆",
    "instruct": "指令克隆",
    "sft": "预训练音色",
}

MODE_ALIASES = {
    "prompt_clone": "zero_shot",
    "prompt-clone": "zero_shot",
    "clone": "zero_shot",
    "clone_with_prompt": "zero_shot",
    "voice_clone": "zero_shot",
    "zero_shot": "zero_shot",
    "zero-shot": "zero_shot",
    "3s极速复刻": "zero_shot",
    "零样本复制": "zero_shot",
    "语音克隆": "zero_shot",
    "cross_lingual": "cross_lingual",
    "cross-lingual": "cross_lingual",
    "fine_grained": "cross_lingual",
    "fine-grained": "cross_lingual",
    "跨语种复刻": "cross_lingual",
    "跨语种克隆": "cross_lingual",
    "精细控制": "cross_lingual",
    "instruct": "instruct",
    "instruction": "instruct",
    "instruction_control": "instruct",
    "voice_design": "instruct",
    "自然语言控制": "instruct",
    "指令控制": "instruct",
    "指令模式": "instruct",
    "指令克隆": "instruct",
    "sft": "sft",
    "preset": "sft",
    "pretrained": "sft",
    "preset_voice": "sft",
    "preset-voice": "sft",
    "预训练音色": "sft",
}


def strip_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = strip_text(value)
        if text:
            return text
    return ""


def normalize_mode_name(value: Any) -> str:
    text = strip_text(value)
    if not text:
        return ""
    normalized_key = text.lower().replace(" ", "_")
    return MODE_ALIASES.get(text, MODE_ALIASES.get(normalized_key, normalized_key))


def profile_mode_name(value: Any) -> str:
    text = strip_text(value)
    if not text:
        return "prompt_clone"
    normalized_key = text.lower().replace(" ", "_")
    if normalized_key in {"prompt_clone", "prompt-clone"}:
        return "prompt_clone"
    engine_mode = normalize_mode_name(text)
    if engine_mode == "zero_shot" and normalized_key not in {"zero_shot", "zero-shot"}:
        return "prompt_clone"
    return engine_mode


def mode_label(value: Any) -> str:
    text = strip_text(value)
    if text in MODE_LABELS:
        return MODE_LABELS[text]
    mode = normalize_mode_name(value)
    return MODE_LABELS.get(mode, text or "")


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def write_toml_mapping(path: Path, payload: dict[str, Any]) -> None:
    scalar_lines: list[str] = []
    nested: list[tuple[str, dict[str, Any]]] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            scalar_lines.append(f"{key} = {toml_value(value)}")
    lines = scalar_lines[:]
    for table, values in nested:
        lines.append("")
        lines.append(f"[{table}]")
        for key, value in values.items():
            lines.append(f"{key} = {toml_value(value)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        payload = tomllib.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"TOML file must contain a table: {path}")
    return payload


def profile_path_text(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    with suppress(ValueError):
        return resolved.relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    return str(resolved)


def resolve_optional_path(raw_path: Any, *, profile_path: Path | None = None, repo_dir: Path = DEFAULT_REPO_DIR) -> str:
    path_text = strip_text(raw_path)
    if not path_text:
        return ""

    candidate = Path(path_text).expanduser()
    if candidate.is_absolute():
        return str(candidate)

    bases: list[Path] = []
    if profile_path is not None:
        bases.append(profile_path.parent)
    bases.extend([WORKSPACE_ROOT, repo_dir, Path.cwd()])
    for base in bases:
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return str(resolved)
    return str((WORKSPACE_ROOT / candidate).resolve())


@dataclass(frozen=True)
class ModelPreset:
    id: str
    name: str
    engine: str = "cosyvoice3"
    model_dir: str = str(DEFAULT_MODEL_DIR)
    fp16: bool = False
    load_jit: bool = False
    load_trt: bool = False
    load_vllm: bool = False
    trt_concurrent: int = 1

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], *, preset_path: Path) -> "ModelPreset":
        preset_id = first_non_empty(payload.get("id"), preset_path.stem, DEFAULT_MODEL_PRESET_ID)
        cosyvoice3 = payload.get("cosyvoice3") if isinstance(payload.get("cosyvoice3"), dict) else {}
        model_dir = resolve_optional_path(
            first_non_empty(cosyvoice3.get("model_dir"), payload.get("model_dir"), DEFAULT_MODEL_DIR),
            profile_path=preset_path,
        )
        return cls(
            id=preset_id,
            name=first_non_empty(payload.get("name"), preset_id),
            engine=first_non_empty(payload.get("engine"), "cosyvoice3"),
            model_dir=model_dir,
            fp16=bool(cosyvoice3.get("fp16", payload.get("fp16", False))),
            load_jit=bool(cosyvoice3.get("load_jit", payload.get("load_jit", False))),
            load_trt=bool(cosyvoice3.get("load_trt", payload.get("load_trt", False))),
            load_vllm=bool(cosyvoice3.get("load_vllm", payload.get("load_vllm", False))),
            trt_concurrent=int(cosyvoice3.get("trt_concurrent", payload.get("trt_concurrent", 1)) or 1),
        )

    def to_native_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "object": "cosyvoice3.model_preset",
            "name": self.name,
            "engine": self.engine,
            "model_dir": self.model_dir,
            "fp16": self.fp16,
            "load_jit": self.load_jit,
            "load_trt": self.load_trt,
            "load_vllm": self.load_vllm,
            "trt_concurrent": self.trt_concurrent,
        }


@dataclass(frozen=True)
class VoiceSet:
    id: str
    name: str
    description: str = ""
    voices: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], *, voice_set_path: Path) -> "VoiceSet":
        set_id = first_non_empty(payload.get("id"), voice_set_path.stem, DEFAULT_VOICE_SET_ID)
        voices = payload.get("voices") if isinstance(payload.get("voices"), list) else []
        return cls(
            id=set_id,
            name=first_non_empty(payload.get("name"), set_id),
            description=strip_text(payload.get("description")),
            voices=tuple(strip_text(item) for item in voices if strip_text(item)),
        )

    def to_openai_model(self, voice_count: int) -> dict[str, Any]:
        return {
            "id": self.id,
            "object": "model",
            "owned_by": "neiroha",
            "name": self.name,
            "description": self.description,
            "voice_count": voice_count,
        }


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    name: str
    mode: str = "prompt_clone"
    model_preset: str = DEFAULT_MODEL_PRESET_ID
    reference_audio: str = ""
    prompt_audio: str = ""
    prompt_text: str = ""
    text_lang: str = "zh"
    prompt_lang: str = "zh"
    instruction: str = ""
    sft_spk: str = ""
    speed: float = 1.0
    description: str = ""
    color: str = ""
    voice_set_id: str = DEFAULT_VOICE_SET_ID
    voice_set_name: str = "Default"
    engine_options: dict[str, Any] | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        profile_path: Path,
        voice_set: VoiceSet | None = None,
    ) -> "VoiceProfile":
        profile_id = first_non_empty(payload.get("id"), payload.get("voice_id"), payload.get("name"))
        if not profile_id:
            raise ValueError("Voice profile requires id or name.")

        engine_options = payload.get("engine_options") if isinstance(payload.get("engine_options"), dict) else {}
        reference_audio = first_non_empty(
            payload.get("reference_audio"),
            payload.get("reference_audio_path"),
            payload.get("ref_audio_path"),
        )
        prompt_audio = first_non_empty(
            payload.get("prompt_audio"),
            payload.get("prompt_audio_path"),
            payload.get("audio_path"),
        )
        instruction = first_non_empty(
            payload.get("instruction"),
            payload.get("instruct_text"),
            payload.get("instruction_text"),
            payload.get("instructions"),
            payload.get("voice_instruction"),
        )
        speaker_id = first_non_empty(
            payload.get("sft_spk"),
            payload.get("spk_id"),
            engine_options.get("speaker_id"),
        )
        voice_set_id = voice_set.id if voice_set is not None else DEFAULT_VOICE_SET_ID
        voice_set_name = voice_set.name if voice_set is not None else "Default"
        return cls(
            id=profile_id,
            name=first_non_empty(payload.get("name"), profile_id),
            mode=profile_mode_name(payload.get("mode")),
            model_preset=first_non_empty(payload.get("model_preset"), DEFAULT_MODEL_PRESET_ID),
            reference_audio=resolve_optional_path(reference_audio, profile_path=profile_path),
            prompt_audio=resolve_optional_path(prompt_audio, profile_path=profile_path),
            prompt_text=first_non_empty(payload.get("prompt_text"), payload.get("reference_text")),
            text_lang=first_non_empty(payload.get("text_lang"), "zh"),
            prompt_lang=first_non_empty(payload.get("prompt_lang"), payload.get("reference_lang"), "zh"),
            instruction=instruction,
            sft_spk=speaker_id,
            speed=float(payload.get("speed", 1.0) or 1.0),
            description=strip_text(payload.get("description")),
            color=strip_text(payload.get("color")),
            voice_set_id=voice_set_id,
            voice_set_name=voice_set_name,
            engine_options={str(k): v for k, v in engine_options.items()},
        )

    @property
    def engine_mode(self) -> str:
        return normalize_mode_name(self.mode)

    @property
    def mode_label(self) -> str:
        return mode_label(self.mode)

    @property
    def prompt_audio_path(self) -> str:
        return first_non_empty(self.prompt_audio, self.reference_audio)

    @property
    def instruct_text(self) -> str:
        return self.instruction

    @property
    def has_prompt_audio(self) -> bool:
        path = self.prompt_audio_path
        return bool(path and Path(path).exists())

    def with_voice_set(self, voice_set: VoiceSet) -> "VoiceProfile":
        return replace(self, voice_set_id=voice_set.id, voice_set_name=voice_set.name)

    def to_profile_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "engine_mode": self.engine_mode,
            "mode_label": self.mode_label,
            "model_preset": self.model_preset,
            "model": self.voice_set_id,
            "description": self.description,
            "reference_audio": profile_path_text(self.prompt_audio_path) if self.prompt_audio_path else "",
            "has_prompt_audio": self.has_prompt_audio,
            "has_prompt_text": bool(self.prompt_text),
            "has_instruct_text": bool(self.instruct_text),
            "sft_spk": self.sft_spk,
        }

    def to_speaker_item(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "voice_id": self.id,
            "model": self.voice_set_id,
            "mode": self.mode,
            "model_preset": self.model_preset,
        }

    def to_openai_voice_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "voice_id": self.id,
            "name": self.name,
            "object": "voice",
            "description": self.description,
            "provider": "CosyVoice3",
            "model": self.voice_set_id,
            "task_mode": self.mode,
            "engine_mode": self.engine_mode,
            "mode_label": self.mode_label,
            "model_preset": self.model_preset,
        }


class VoiceRegistry:
    def __init__(
        self,
        profile_path: Path | str = DEFAULT_PROFILE_PATH,
        *,
        config_root: Path | str = CONFIG_ROOT,
        voices_root: Path | str = RUNTIME_VOICES_ROOT,
    ) -> None:
        self.profile_path = Path(profile_path)
        self.config_root = Path(config_root)
        self.voices_root = Path(voices_root)
        self.model_presets_dir = self.config_root / "model-presets"
        self.voice_sets_dir = self.config_root / "voice-sets"
        self.server_config_path = self.config_root / "server.toml"
        self._legacy_profile_only = (
            self.profile_path.exists()
            and self.profile_path.resolve() != DEFAULT_PROFILE_PATH.resolve()
        )

    def server_config(self) -> dict[str, Any]:
        if self.server_config_path.exists():
            return read_toml(self.server_config_path)
        return {
            "api": {"host": "127.0.0.1", "port": 19890, "preload_model": False},
            "admin": {"enabled": True, "host": "127.0.0.1", "port": 17870},
            "ui": {"title": "Neiroha CosyVoice3 Admin", "default_language": "zh"},
            "runtime": {
                "active_model_preset": DEFAULT_MODEL_PRESET_ID,
                "active_voice_set": DEFAULT_VOICE_SET_ID,
                "default_voice": DEFAULT_VOICE_ID,
            },
        }

    def active_model_preset_id(self) -> str:
        runtime = self.server_config().get("runtime", {})
        if isinstance(runtime, dict):
            return first_non_empty(runtime.get("active_model_preset"), DEFAULT_MODEL_PRESET_ID)
        return DEFAULT_MODEL_PRESET_ID

    def active_voice_set_id(self) -> str:
        runtime = self.server_config().get("runtime", {})
        if isinstance(runtime, dict):
            return first_non_empty(runtime.get("active_voice_set"), DEFAULT_VOICE_SET_ID)
        return DEFAULT_VOICE_SET_ID

    def default_voice_id(self) -> str:
        runtime = self.server_config().get("runtime", {})
        configured = first_non_empty(runtime.get("default_voice") if isinstance(runtime, dict) else "", DEFAULT_VOICE_ID)
        if self.get_optional(configured, voice_set_id=self.active_voice_set_id()) is not None:
            return configured
        profiles = self.list_profiles(self.active_voice_set_id())
        return profiles[0].id if profiles else configured

    def list_model_presets(self) -> list[ModelPreset]:
        presets: list[ModelPreset] = []
        for path in sorted(self.model_presets_dir.glob("*.toml")):
            try:
                presets.append(ModelPreset.from_mapping(read_toml(path), preset_path=path))
            except Exception:
                continue
        if presets:
            return presets
        return [
            ModelPreset(
                id=DEFAULT_MODEL_PRESET_ID,
                name="CosyVoice3 Default",
                model_dir=str(DEFAULT_MODEL_DIR),
            )
        ]

    def get_model_preset(self, preset_id: str | None = None) -> ModelPreset:
        requested = first_non_empty(preset_id, self.active_model_preset_id())
        for preset in self.list_model_presets():
            if requested.lower() in {preset.id.lower(), preset.name.lower()}:
                return preset
        raise KeyError(f"Model preset not found: {requested}")

    def list_voice_sets(self) -> list[VoiceSet]:
        voice_sets: list[VoiceSet] = []
        if self._legacy_profile_only:
            legacy_profiles = self._list_legacy_json_profiles()
            return [
                VoiceSet(
                    id=DEFAULT_VOICE_SET_ID,
                    name="Default",
                    description="Legacy JSON voice profiles.",
                    voices=tuple(profile.id for profile in legacy_profiles),
                )
            ]
        for path in sorted(self.voice_sets_dir.glob("*.toml")):
            try:
                voice_sets.append(VoiceSet.from_mapping(read_toml(path), voice_set_path=path))
            except Exception:
                continue
        if voice_sets:
            return voice_sets
        legacy_profiles = self._list_legacy_json_profiles()
        return [
            VoiceSet(
                id=DEFAULT_VOICE_SET_ID,
                name="Default",
                description="Legacy JSON voice profiles.",
                voices=tuple(profile.id for profile in legacy_profiles),
            )
        ]

    def get_voice_set(self, voice_set_id: str | None = None) -> VoiceSet:
        requested = first_non_empty(voice_set_id, self.active_voice_set_id())
        for voice_set in self.list_voice_sets():
            if requested.lower() in {voice_set.id.lower(), voice_set.name.lower()}:
                return voice_set
        raise KeyError(f"Voice set not found: {requested}")

    def _load_voice_profile(self, voice_id: str, voice_set: VoiceSet) -> VoiceProfile | None:
        path = self.voices_root / voice_id / "voice.toml"
        if not path.exists():
            return None
        try:
            return VoiceProfile.from_mapping(read_toml(path), profile_path=path, voice_set=voice_set)
        except Exception:
            return None

    def list_profiles(self, voice_set_id: str | None = None) -> list[VoiceProfile]:
        if self._legacy_profile_only:
            return self._list_legacy_json_profiles()
        if self.voice_sets_dir.exists() and any(self.voice_sets_dir.glob("*.toml")):
            voice_sets = self.list_voice_sets()
            if voice_set_id:
                lowered = voice_set_id.lower()
                voice_sets = [
                    voice_set
                    for voice_set in voice_sets
                    if lowered in {voice_set.id.lower(), voice_set.name.lower()}
                ]
            profiles: list[VoiceProfile] = []
            seen: set[tuple[str, str]] = set()
            for voice_set in voice_sets:
                voice_ids = voice_set.voices or tuple(path.parent.name for path in sorted(self.voices_root.glob("*/voice.toml")))
                for voice_id in voice_ids:
                    profile = self._load_voice_profile(voice_id, voice_set)
                    if profile is not None and (voice_set.id, profile.id) not in seen:
                        profiles.append(profile)
                        seen.add((voice_set.id, profile.id))
            return profiles
        return self._list_legacy_json_profiles()

    def _list_legacy_json_profiles(self) -> list[VoiceProfile]:
        if not self.profile_path.exists():
            return []
        data = json.loads(self.profile_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("voices", data.get("profiles", []))
        if not isinstance(data, list):
            raise ValueError(f"Profile file must be a list or a voices object: {self.profile_path}")
        profiles: list[VoiceProfile] = []
        voice_set = VoiceSet(id=DEFAULT_VOICE_SET_ID, name="Default")
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                profiles.append(VoiceProfile.from_mapping(item, profile_path=self.profile_path, voice_set=voice_set))
            except ValueError:
                continue
        return profiles

    def get_optional(self, profile_id: str, *, voice_set_id: str | None = None) -> VoiceProfile | None:
        profile_id = strip_text(profile_id)
        if not profile_id:
            return None
        lowered = profile_id.lower()
        for profile in self.list_profiles(voice_set_id):
            if lowered in {profile.id.lower(), profile.name.lower()}:
                return profile
        return None

    def save_voice_profile(
        self,
        *,
        voice_set_id: str,
        model_preset: str,
        voice_id: str,
        name: str,
        mode: str,
        reference_audio: str,
        prompt_text: str = "",
        prompt_lang: str = "zh",
        text_lang: str = "zh",
        instruction: str = "",
        speed: float = 1.0,
        upload_path: str = "",
    ) -> VoiceProfile:
        voice_id = strip_text(voice_id)
        if not voice_id:
            raise ValueError("voice id is required")
        if not first_non_empty(upload_path, reference_audio):
            raise ValueError("reference audio is required")

        voice_dir = self.voices_root / voice_id
        voice_dir.mkdir(parents=True, exist_ok=True)
        final_reference = strip_text(reference_audio)
        if upload_path:
            source = Path(upload_path)
            suffix = source.suffix or ".wav"
            target = voice_dir / f"reference{suffix}"
            shutil.copyfile(source, target)
            final_reference = profile_path_text(target)

        payload = {
            "schema_version": 1,
            "id": voice_id,
            "name": first_non_empty(name, voice_id),
            "mode": profile_mode_name(mode),
            "model_preset": first_non_empty(model_preset, self.active_model_preset_id()),
            "reference_audio": final_reference,
            "prompt_audio": "",
            "prompt_text": prompt_text,
            "text_lang": first_non_empty(text_lang, "zh"),
            "prompt_lang": first_non_empty(prompt_lang, "zh"),
            "instruction": instruction,
            "speed": float(speed or 1.0),
            "engine_options": {
                "speaker_id": "",
                "speaker_embedding_path": "",
                "adapter_path": "",
            },
        }
        path = voice_dir / "voice.toml"
        write_toml_mapping(path, payload)
        self._ensure_voice_in_set(voice_set_id, voice_id)
        return VoiceProfile.from_mapping(read_toml(path), profile_path=path, voice_set=self.get_voice_set(voice_set_id))

    def _ensure_voice_in_set(self, voice_set_id: str, voice_id: str) -> None:
        voice_set = self.get_voice_set(voice_set_id)
        voices = list(voice_set.voices)
        if voice_id not in voices:
            voices.append(voice_id)
        path = self.voice_sets_dir / f"{voice_set.id}.toml"
        write_toml_mapping(
            path,
            {
                "schema_version": 1,
                "id": voice_set.id,
                "name": voice_set.name,
                "description": voice_set.description,
                "voices": voices,
            },
        )
