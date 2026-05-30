# Model Sources

Large model assets are not committed to this repository. The local home for
downloaded assets is `models/`; generated caches stay under `models/_cache/`
or `runtime/cache/`.

## Default Preset

`configs/model-presets/default.toml` points to:

```text
models/Fun-CosyVoice3-0.5B
```

Download task:

```powershell
pixi run install
```

Default source:

- ModelScope: `FunAudioLLM/Fun-CosyVoice3-0.5B-2512`
- Hugging Face compatible id: `FunAudioLLM/Fun-CosyVoice3-0.5B-2512`

## Frontend Assets

Windows installs `wetext` by default because the local CosyVoice frontend uses
it on this platform:

```text
models/_cache/modelscope/models/pengzhendong/wetext
```

Optional task:

```powershell
pixi run install-wetext
```

Non-Windows environments can use `CosyVoice-ttsfrd`:

```powershell
pixi run install-ttsfrd
```

Expected local path:

```text
models/CosyVoice-ttsfrd
```

## Download Policy

Download actions are explicit. `pixi run api`, `pixi run admin`, and
`pixi run serve` do not hide multi-GB downloads behind ordinary startup.
Downloader destinations are validated so assets remain under `models/`.
