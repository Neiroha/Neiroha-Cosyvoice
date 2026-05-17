# Neiroha CosyVoice Local Service

CosyVoice native service for Neiroha. The outer repository owns Pixi, FastAPI,
Gradio, profiles and runtime files. The official
[FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) repository is
kept as the `CosyVoice/` Git submodule.

## Quick Start

```powershell
pixi install
pixi run submodule-init
pixi run install
Copy-Item profiles/voices.example.json profiles/voices.json
pixi run clone-smoke
pixi run combined
```

FastAPI is served from `http://127.0.0.1:9880`; Gradio is mounted at
`http://127.0.0.1:9880/gradio` in `combined` mode.

`pixi run install` uses ModelScope by default. It downloads the default
CosyVoice3 runtime model `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` to
`models/Fun-CosyVoice3-0.5B` and the matching `CosyVoice-ttsfrd` text frontend
resource to `models/CosyVoice-ttsfrd`. All ModelScope, Hugging Face,
Transformers, Torch and temp caches are forced under this project, mainly
`models/_cache` and `runtime/temp`; the downloader rejects destinations outside
`./models`.

The official CosyVoice frontend looks for `CosyVoice/pretrained_models` at
runtime. The launcher creates only a local junction/symlink from that expected
path to `models/CosyVoice-ttsfrd`; the resource itself stays under `./models`.

## Run Modes

```powershell
pixi run api
pixi run api-preload
pixi run webui
pixi run combined
pixi run clone-smoke
```

Useful direct launcher example:

```powershell
pixi run python scripts/launch_cosyvoice.py --mode api --model-dir models/Fun-CosyVoice3-0.5B --port 12080 --preload-model
```

## API Surface

Neiroha CosyVoice native adapter:

- `GET /health`
- `GET /speakers`
- `GET /cosyvoice/profiles`
- `POST /cosyvoice/speech`
- `POST /cosyvoice/speech/upload`

OpenAI compatible:

- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`

See [docs/api.md](docs/api.md) for payload examples.

## Profiles

Copy `profiles/voices.example.json` to `profiles/voices.json` and edit local
audio paths. The service reads the file on each request, so profile edits do
not require a server restart.

Supported profile modes:

- `zero_shot`
- `cross_lingual`
- `instruct`

For CosyVoice 3, the launcher applies the required `<|endofprompt|>` prompt
formatting used by the official examples.
