# Neiroha CosyVoice3 API

Default FastAPI base URL: `http://127.0.0.1:19890`.

## OpenAI Compatible

`GET /v1/models` returns voice sets:

```json
{
  "object": "list",
  "data": [
    {
      "id": "default",
      "object": "model",
      "owned_by": "neiroha",
      "name": "Default",
      "voice_count": 3
    }
  ]
}
```

`GET /v1/audio/voices` returns voice profiles:

```json
{
  "object": "list",
  "data": [
    {
      "id": "prompt-clone",
      "voice_id": "prompt-clone",
      "name": "Prompt Clone",
      "object": "voice",
      "model": "default",
      "task_mode": "prompt_clone",
      "engine_mode": "zero_shot",
      "model_preset": "cosyvoice3-default"
    }
  ]
}
```

`POST /v1/audio/speech`:

```json
{
  "model": "default",
  "voice": "prompt-clone",
  "input": "你好，这是 CosyVoice3 的语音复刻测试。",
  "response_format": "wav",
  "speed": 1.0
}
```

Response headers:

```text
X-Neiroha-Output-Path
X-Neiroha-Audio-Seconds
X-Neiroha-Elapsed-Seconds
X-Neiroha-RTF
X-Neiroha-CosyVoice-Mode
```

Output filenames are ASCII-safe so Chinese voice ids are valid in FastAPI /
Starlette response headers.

## Native CosyVoice

- `GET /health`
- `GET /speakers`
- `GET /cosyvoice/profiles`
- `GET /cosyvoice/meta`
- `GET /cosyvoice3/capabilities`
- `GET /cosyvoice3/logs`
- `POST /cosyvoice/speech`
- `POST /cosyvoice/speech/upload`

`POST /cosyvoice/speech` JSON body:

```json
{
  "text": "要合成的文本",
  "mode": "prompt_clone",
  "model": "default",
  "voice": "prompt-clone",
  "prompt_audio_path": "CosyVoice/asset/zero_shot_prompt.wav",
  "prompt_text": "参考音频对应文本",
  "speed": 1.0,
  "response_format": "wav"
}
```

Supported CosyVoice3 clone modes:

- `prompt_clone` / `zero_shot`: requires `prompt_audio_path` or profile reference audio, plus `prompt_text`.
- `cross_lingual`: requires `prompt_audio_path` or profile reference audio.
- `instruct`: requires `prompt_audio_path` or profile reference audio, plus `instruct_text` / `instruction`.

`POST /cosyvoice/speech/upload` uses `multipart/form-data` with the same text
fields plus `prompt_audio` as the uploaded reference audio file.

## Local Model Policy

The default install path is CosyVoice3 plus the matching `CosyVoice-ttsfrd`
resource. Both are stored under project-local `./models`; ModelScope is the
default download source. CosyVoice2 is not part of the default install path.
