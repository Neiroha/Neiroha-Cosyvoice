from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from typing import Any

CONTENT_TYPES = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "pcm": "audio/pcm",
    "raw": "application/octet-stream",
    "wav": "audio/wav",
}


@dataclass(frozen=True)
class PackedAudio:
    content: bytes
    media_type: str
    extension: str


def normalize_audio_array(audio: Any):
    import numpy as np
    import torch

    if isinstance(audio, torch.Tensor):
        data = audio.detach().cpu().float().numpy()
    else:
        data = np.asarray(audio, dtype=np.float32)

    if data.ndim == 2:
        if data.shape[0] <= data.shape[1]:
            data = data[0]
        else:
            data = data[:, 0]
    return np.clip(data.astype(np.float32), -1.0, 1.0)


def audio_duration_seconds(audio: Any, sample_rate: int) -> float:
    data = normalize_audio_array(audio)
    if sample_rate <= 0:
        return 0.0
    return float(data.shape[0] / sample_rate)


def _int16_pcm(audio: Any) -> bytes:
    import numpy as np

    data = normalize_audio_array(audio)
    return (data * 32767.0).astype("<i2").tobytes()


def _pack_soundfile(audio: Any, sample_rate: int, fmt: str) -> bytes:
    import soundfile as sf

    data = normalize_audio_array(audio)
    buffer = io.BytesIO()
    sf_format = {"wav": "WAV", "flac": "FLAC", "ogg": "OGG"}.get(fmt)
    if sf_format is None:
        raise ValueError(f"Unsupported soundfile format: {fmt}")
    sf.write(buffer, data, sample_rate, format=sf_format)
    return buffer.getvalue()


def _pack_ffmpeg(audio: Any, sample_rate: int, fmt: str) -> bytes:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        "-vn",
    ]
    if fmt == "mp3":
        command += ["-f", "mp3", "pipe:1"]
    elif fmt == "aac":
        command += ["-c:a", "aac", "-b:a", "192k", "-f", "adts", "pipe:1"]
    elif fmt == "opus":
        command += ["-c:a", "libopus", "-b:a", "64k", "-f", "ogg", "pipe:1"]
    else:
        raise ValueError(f"Unsupported ffmpeg format: {fmt}")

    process = subprocess.run(
        command,
        input=_int16_pcm(audio),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed to encode {fmt}: {detail}")
    return process.stdout


def pack_audio(audio: Any, sample_rate: int, response_format: str) -> PackedAudio:
    fmt = (response_format or "wav").strip().lower()
    if fmt not in CONTENT_TYPES:
        raise ValueError(f"Unsupported response_format: {fmt}")

    if fmt in {"pcm", "raw"}:
        content = _int16_pcm(audio)
    elif fmt in {"wav", "flac", "ogg"}:
        content = _pack_soundfile(audio, sample_rate, fmt)
    else:
        content = _pack_ffmpeg(audio, sample_rate, fmt)

    extension = "pcm" if fmt == "raw" else fmt
    return PackedAudio(content=content, media_type=CONTENT_TYPES[fmt], extension=extension)

