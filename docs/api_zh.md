# Neiroha CosyVoice3 API

默认 FastAPI 地址：`http://127.0.0.1:19890`。

## OpenAI 兼容路由

- `GET /v1/models`：返回 voice set，`id` 可作为 `/v1/audio/speech` 的 `model`。
- `GET /v1/audio/voices`：返回 voice set 下的 voice 配置。
- `POST /v1/audio/speech`：合成语音。

示例：

```json
{
  "model": "default",
  "voice": "prompt-clone",
  "input": "你好，这是 CosyVoice3 的语音复刻测试。",
  "response_format": "wav",
  "speed": 1.0
}
```

常用响应头：

```text
X-Neiroha-Backend
X-Neiroha-Model-Preset
X-Neiroha-Voice
X-Neiroha-Sample-Rate
X-Neiroha-Inference-Ms
X-Neiroha-Output-Format
X-Neiroha-Output-Path
X-Neiroha-Audio-Seconds
X-Neiroha-Elapsed-Seconds
X-Neiroha-RTF
```

## Native CosyVoice 路由

- `GET /health`
- `GET /api/cosyvoice/voices`
- `GET /api/cosyvoice/meta`
- `GET /api/cosyvoice/capabilities`
- `GET /api/cosyvoice/logs`
- `POST /api/cosyvoice/tts`
- `POST /api/cosyvoice/tts/upload`

旧路由仍保留兼容：

- `GET /cosyvoice/profiles`
- `GET /cosyvoice/meta`
- `GET /cosyvoice3/capabilities`
- `GET /cosyvoice3/logs`
- `POST /cosyvoice/speech`
- `POST /cosyvoice/speech/upload`

## 错误格式

```json
{
  "error": {
    "code": "voice_not_found",
    "message": "Voice set was not found.",
    "details": {},
    "type": "invalid_request_error",
    "param": null
  }
}
```

稳定错误码包括：`voice_not_found`、`model_preset_not_found`、
`model_not_loaded`、`unsupported_format`、`invalid_reference_audio`、
`inference_failed`、`engine_unavailable`、`auth_required`。
