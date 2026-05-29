# Neiroha CosyVoice3 Local Service

CosyVoice3 native service for Neiroha. The outer repository owns Pixi,
FastAPI, Gradio Admin, TOML configuration and runtime files. The official
[FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) repository is
kept as the `CosyVoice/` Git submodule.

## Quick Start

```powershell
pixi install
pixi run submodule-init
pixi run install
pixi run clone-smoke
pixi run api-admin
```

Chinese documentation is available in [README_zh.md](README_zh.md).

`pixi run api-admin` reads ports and preload behavior from `configs/server.toml`.
Defaults are:

- FastAPI: `http://127.0.0.1:19890`
- Gradio Admin: `http://127.0.0.1:17870`
- `preload_model = true`

If a configured port is unavailable, the launcher picks a random bindable port
and records the actual URL in `runtime/logs/backend.log` and `/health`.

`pixi run install` uses ModelScope by default. It downloads the default
CosyVoice3 runtime model `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` to
`models/Fun-CosyVoice3-0.5B`. On Windows, CosyVoice falls back to `wetext`, so
the default install also pre-downloads `pengzhendong/wetext` into
`models/_cache/modelscope/models/pengzhendong/wetext`. On non-Windows systems,
the auto frontend target remains `CosyVoice-ttsfrd`; `pixi run install-ttsfrd`
is also available explicitly. ModelScope, Hugging Face, Transformers, Torch and
temp caches are forced under this project, mainly `models/_cache` and
`runtime/temp`; the downloader rejects destinations outside `./models`.

## Configuration

Local configuration is TOML-first:

```text
configs/server.toml
configs/model-presets/default.toml
configs/voice-sets/default.toml
runtime/voices/prompt-clone/voice.toml
runtime/voices/cross-lingual-clone/voice.toml
runtime/voices/instruct-clone/voice.toml
```

OpenAI-compatible `model` means voice set, not the underlying CosyVoice3
checkpoint. The active checkpoint is selected by a model preset, and each
voice profile can point at a preset through `model_preset`.

Default clone voice configs keep the three CosyVoice3 native clone paths:

- `prompt_clone`: CosyVoice3 zero-shot clone with prompt text.
- `cross_lingual`: prompt-audio clone without prompt text.
- `instruct`: CosyVoice3 instruct clone with prompt audio and instruction.

## Run Modes

```powershell
pixi run api
pixi run api-preload
pixi run admin
pixi run api-admin
pixi run api-admin-preload
```

Useful download tasks:

```powershell
pixi run install
pixi run install-wetext
pixi run install-ttsfrd
```

`api-admin` starts FastAPI and an independent Gradio Admin process. Gradio is
not mounted into FastAPI by default.

## API Surface

Neiroha CosyVoice native adapter:

- `GET /health`
- `GET /speakers`
- `GET /cosyvoice/profiles`
- `GET /cosyvoice/meta`
- `GET /cosyvoice3/capabilities`
- `GET /cosyvoice3/logs`
- `POST /cosyvoice/speech`
- `POST /cosyvoice/speech/upload`

OpenAI compatible:

- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`

See [docs/api.md](docs/api.md) for payload examples.
