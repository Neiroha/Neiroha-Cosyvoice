# Neiroha CosyVoice API

Default FastAPI base URL: `http://127.0.0.1:9880`.

## Native CosyVoice

- `GET /health`
- `GET /speakers`
- `GET /cosyvoice/profiles`
- `GET /cosyvoice/meta`
- `POST /cosyvoice/speech`
- `POST /cosyvoice/speech/upload`

`POST /cosyvoice/speech` JSON body:

```json
{
  "text": "要合成的文本",
  "mode": "zero_shot",
  "profile": "demo-zero-shot",
  "prompt_audio_path": "D:/voices/reference.wav",
  "prompt_text": "参考音频对应文本",
  "instruct_text": "用温柔平静的语气朗读",
  "speed": 1.0,
  "response_format": "wav"
}
```

`POST /cosyvoice/speech/upload` uses `multipart/form-data` with the same text
fields plus `prompt_audio` as the uploaded reference audio file. Neiroha's
CosyVoice native adapter intentionally does not send `profile` for this route.

## OpenAI Compatible

- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`

```json
{
  "model": "cosyvoice-openai-tts",
  "voice": "demo-zero-shot",
  "input": "你好，欢迎使用 Neiroha。",
  "response_format": "wav"
}
```

## Modes

- `zero_shot`: requires `prompt_audio_path` or `prompt_audio`, plus `prompt_text`
- `cross_lingual`: requires `prompt_audio_path` or `prompt_audio`
- `instruct`: requires `prompt_audio_path` or `prompt_audio`, plus `instruct_text`
The default project download target is CosyVoice3 plus the matching
`CosyVoice-ttsfrd` text frontend resource. Both are stored under project-local
`./models`; ModelScope is the default download source. CosyVoice2 is not part
of the default install path.
