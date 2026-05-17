from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import WORKSPACE_ROOT

MODE_LABELS = {
    "zero_shot": "语音克隆",
    "cross_lingual": "精细控制",
    "instruct": "指令模式",
    "sft": "预训练音色",
}

MODE_ALIASES = {
    "zero_shot": "zero_shot",
    "zero-shot": "zero_shot",
    "clone": "zero_shot",
    "clone_with_prompt": "zero_shot",
    "voice_clone": "zero_shot",
    "3s极速复刻": "zero_shot",
    "零样本复制": "zero_shot",
    "语音克隆": "zero_shot",
    "cross_lingual": "cross_lingual",
    "cross-lingual": "cross_lingual",
    "fine_grained": "cross_lingual",
    "fine-grained": "cross_lingual",
    "跨语种复刻": "cross_lingual",
    "精细控制": "cross_lingual",
    "instruct": "instruct",
    "instruction": "instruct",
    "instruction_control": "instruct",
    "voice_design": "instruct",
    "自然语言控制": "instruct",
    "指令控制": "instruct",
    "指令模式": "instruct",
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


def mode_label(value: Any) -> str:
    mode = normalize_mode_name(value)
    return MODE_LABELS.get(mode, strip_text(value) or "")


def _resolve_profile_path(raw_path: Any, *, profile_path: Path) -> str:
    path_text = strip_text(raw_path)
    if not path_text:
        return ""

    candidate = Path(path_text).expanduser()
    if candidate.is_absolute():
        return str(candidate)

    for base in (profile_path.parent, WORKSPACE_ROOT, Path.cwd()):
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return str(resolved)
    return str((WORKSPACE_ROOT / candidate).resolve())


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    name: str
    mode: str = "zero_shot"
    prompt_audio: str = ""
    prompt_text: str = ""
    instruct_text: str = ""
    prompt_lang: str = ""
    sft_spk: str = ""
    description: str = ""
    color: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], *, profile_path: Path) -> "VoiceProfile":
        profile_id = first_non_empty(payload.get("id"), payload.get("name"), payload.get("voice_id"))
        if not profile_id:
            raise ValueError("Voice profile requires id or name.")

        prompt_audio = first_non_empty(
            payload.get("prompt_audio"),
            payload.get("prompt_audio_path"),
            payload.get("reference_audio_path"),
            payload.get("ref_audio_path"),
            payload.get("audio_path"),
        )
        return cls(
            id=profile_id,
            name=first_non_empty(payload.get("name"), profile_id),
            mode=normalize_mode_name(payload.get("mode")) or "zero_shot",
            prompt_audio=_resolve_profile_path(prompt_audio, profile_path=profile_path),
            prompt_text=first_non_empty(payload.get("prompt_text"), payload.get("reference_text")),
            instruct_text=first_non_empty(
                payload.get("instruct_text"),
                payload.get("instruction_text"),
                payload.get("instructions"),
            ),
            prompt_lang=first_non_empty(payload.get("prompt_lang"), payload.get("reference_lang")),
            sft_spk=first_non_empty(payload.get("sft_spk"), payload.get("spk_id")),
            description=strip_text(payload.get("description")),
            color=strip_text(payload.get("color")),
        )

    @property
    def mode_label(self) -> str:
        return mode_label(self.mode)

    @property
    def has_prompt_audio(self) -> bool:
        return bool(self.prompt_audio and Path(self.prompt_audio).exists())

    def to_profile_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "mode_label": self.mode_label,
            "description": self.description,
            "has_prompt_audio": self.has_prompt_audio,
            "has_prompt_text": bool(self.prompt_text),
            "has_instruct_text": bool(self.instruct_text),
            "sft_spk": self.sft_spk,
        }

    def to_speaker_item(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "voice_id": self.id,
            "model": "cosyvoice",
            "mode": self.mode,
        }

    def to_openai_voice_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "voice_id": self.id,
            "name": self.name,
            "object": "voice",
            "description": self.description,
            "provider": "CosyVoice",
            "model": "cosyvoice",
            "task_mode": self.mode,
            "mode_label": self.mode_label,
        }


class VoiceRegistry:
    def __init__(self, profile_path: Path) -> None:
        self.profile_path = profile_path

    def _read_payload(self) -> list[dict[str, Any]]:
        if not self.profile_path.exists():
            return []
        data = json.loads(self.profile_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("voices", data.get("profiles", []))
        if not isinstance(data, list):
            raise ValueError(f"Profile file must be a list or a voices object: {self.profile_path}")
        return [item for item in data if isinstance(item, dict)]

    def list_profiles(self) -> list[VoiceProfile]:
        profiles: list[VoiceProfile] = []
        for item in self._read_payload():
            try:
                profiles.append(VoiceProfile.from_mapping(item, profile_path=self.profile_path))
            except ValueError:
                continue
        return profiles

    def get_optional(self, profile_id: str) -> VoiceProfile | None:
        profile_id = strip_text(profile_id)
        if not profile_id:
            return None
        lowered = profile_id.lower()
        for profile in self.list_profiles():
            if lowered in {profile.id.lower(), profile.name.lower()}:
                return profile
        return None

