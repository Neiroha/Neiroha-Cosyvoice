# Neiroha CosyVoice3 本地服务

这是面向 Neiroha 的独立 CosyVoice3 后端。仓库只维护自己的 Pixi 环境、
FastAPI、Gradio Admin、TOML 配置和运行时目录；官方
`FunAudioLLM/CosyVoice` 作为 `CosyVoice/` 子模块存在。

## 核心语义

- OpenAI TTS 风格 API：`/v1/models`、`/v1/audio/voices`、`/v1/audio/speech`
- `model` 表示 voice set，不表示底层 CosyVoice3 权重
- `voice` 表示 voice set 里的具体声音配置
- 底层 CosyVoice3 权重放在 model preset
- 默认 voice set 是 `default`
- 默认提供三种 CosyVoice3 克隆配置：`prompt_clone`、`cross_lingual`、`instruct`

## 目录语义

```text
configs/
  server.toml
  model-presets/
    default.toml
  voice-sets/
    default.toml
runtime/
  voices/
    prompt-clone/
      voice.toml
    cross-lingual-clone/
      voice.toml
    instruct-clone/
      voice.toml
  logs/
  outputs/
models/
  Fun-CosyVoice3-0.5B/
  _cache/
```

用户侧配置统一使用 TOML。模型权重和缓存默认都在项目内 `./models`，不会写到
C 盘 Hugging Face 缓存目录。

## 安装

```powershell
pixi install
pixi run submodule-init
pixi run install
```

`pixi run install` 默认使用 ModelScope，下载 CosyVoice3：

```text
models/Fun-CosyVoice3-0.5B
```

Windows 下 CosyVoice 实际使用 `wetext` 前端，所以默认安装会同时预热：

```text
models/_cache/modelscope/models/pengzhendong/wetext
```

可选下载任务：

```powershell
pixi run install-wetext
pixi run install-ttsfrd
```

## 启动

```powershell
start_api_admin.bat
```

或使用 Pixi task：

```powershell
pixi run api
pixi run api-preload
pixi run admin
pixi run api-admin
pixi run api-admin-preload
```

默认端口来自 `configs/server.toml`：

```text
FastAPI  http://127.0.0.1:19890
Admin    http://127.0.0.1:17870
```

默认启动会预加载模型：

```toml
[api]
preload_model = true
```

端口被占用时，launcher 会自动挑一个可用随机端口，并在终端、
`runtime/logs/backend.log` 和 `/health` 里写出实际地址。

## Admin 语言

Gradio Admin 支持中文和英文。修改 `configs/server.toml` 后重启 Admin：

```toml
[ui]
default_language = "zh" # zh | en
```

环境变量也可以覆盖：

```powershell
$env:NEIROHA_COSYVOICE3_UI_LANG="en"
```

## API 示例

列出 voice set：

```powershell
curl.exe http://127.0.0.1:19890/v1/models
```

列出 voice：

```powershell
curl.exe http://127.0.0.1:19890/v1/audio/voices
```

语音合成：

```powershell
curl.exe http://127.0.0.1:19890/v1/audio/speech `
  -H "Content-Type: application/json" `
  -d '{ "model":"default", "voice":"prompt-clone", "input":"你好，这是一次 CosyVoice3 语音复刻测试。", "response_format":"wav" }' `
  --output speech.wav
```

响应头包含：

```text
X-Neiroha-Output-Path
X-Neiroha-Audio-Seconds
X-Neiroha-Elapsed-Seconds
X-Neiroha-RTF
```

## 添加自己的 voice

在 Admin 的“克隆配置”页上传参考音频、填写对应文本、设置 voice id/name 并保存。
也可以手动创建：

```text
runtime/voices/my-voice/voice.toml
```

然后把 `my-voice` 加到：

```text
configs/voice-sets/default.toml
```

voice 配置示例：

```toml
schema_version = 1
id = "my-voice"
name = "My Voice"
mode = "prompt_clone"
model_preset = "cosyvoice3-default"
reference_audio = "runtime/voices/my-voice/reference.wav"
prompt_audio = ""
prompt_text = "参考音频对应文本"
text_lang = "zh"
prompt_lang = "zh"
instruction = ""
speed = 1.0

[engine_options]
speaker_id = ""
speaker_embedding_path = ""
adapter_path = ""
```
