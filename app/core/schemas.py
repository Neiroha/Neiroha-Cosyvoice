from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CosyVoiceSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = Field(None, description="Compatibility model field.")
    text: str | None = Field(None, description="Text to synthesize.")
    input: str | None = Field(None, description="OpenAI-compatible alias for text.")
    mode: str | None = Field(None, description="prompt_clone | zero_shot | cross_lingual | instruct | sft")
    profile: str | None = Field(None, description="Registered server profile id or name.")
    character_name: str | None = Field(None, description="Compatibility alias for profile.")
    speaker: str | None = Field(None, description="Compatibility alias for profile.")
    voice: str | dict[str, Any] | None = Field(None, description="Compatibility alias for profile.")
    prompt_audio_path: str | None = Field(None, description="Server-local prompt/reference audio path.")
    reference_audio_path: str | None = Field(None, description="Alias for prompt_audio_path.")
    ref_audio_path: str | None = Field(None, description="Alias for prompt_audio_path.")
    prompt_text: str | None = Field(None, description="Required for zero_shot.")
    reference_text: str | None = Field(None, description="Alias for prompt_text.")
    instruct_text: str | None = Field(None, description="Required for instruct.")
    instruction_text: str | None = Field(None, description="Alias for instruct_text.")
    instructions: str | None = Field(None, description="Alias for instruct_text.")
    voice_instruction: str | None = Field(None, description="Alias for instruct_text.")
    prompt_lang: str | None = Field(None, description="Reserved compatibility field.")
    sft_spk: str | None = Field(None, description="Official SFT speaker id.")
    spk_id: str | None = Field(None, description="Alias for sft_spk.")
    speed: float = Field(1.0, ge=0.25, le=4.0)
    response_format: str = Field("wav", description="wav, mp3, flac, aac, opus, pcm, ogg, raw")
    format: str | None = Field(None, description="Alias for response_format.")
    seed: int | None = Field(None, description="Optional deterministic seed.")
    stream: bool = Field(False, description="Accepted for API compatibility; responses are buffered.")
    text_frontend: bool = Field(True, description="Pass through to CosyVoice text frontend.")


class OpenAISpeechRequest(CosyVoiceSpeechRequest):
    model: str = "default"
    input: str | None = Field(None, description="Text to synthesize.")
    voice: str | dict[str, Any] | None = Field(..., description="Registered profile id/name.")
    response_format: str = "mp3"
