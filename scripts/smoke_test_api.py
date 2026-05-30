from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.core.config import DEFAULT_API_HOST, DEFAULT_API_PORT, OUTPUT_ROOT
from app.core.profiles import VoiceRegistry


def parse_args() -> argparse.Namespace:
    registry = VoiceRegistry()
    api_config = registry.server_config().get("api", {})
    host = api_config.get("host", DEFAULT_API_HOST) if isinstance(api_config, dict) else DEFAULT_API_HOST
    port = api_config.get("port", DEFAULT_API_PORT) if isinstance(api_config, dict) else DEFAULT_API_PORT
    parser = argparse.ArgumentParser(description="Smoke test a running Neiroha CosyVoice API.")
    parser.add_argument("--base-url", default=f"http://{host}:{int(port)}")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--speech", action="store_true", help="Also run /v1/audio/speech against the default voice.")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT / "api_smoke.wav")
    return parser.parse_args()


def request_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def get_json(base_url: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(f"{base_url.rstrip('/')}{path}", headers=headers, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} did not return a JSON object.")
    return payload


def first_data_id(payload: dict[str, Any], path: str) -> str:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"{path} returned no data items.")
    first = data[0]
    if not isinstance(first, dict) or not first.get("id"):
        raise RuntimeError(f"{path} first item has no id.")
    return str(first["id"])


def main() -> None:
    args = parse_args()
    headers = request_headers(args.api_key)
    health = get_json(args.base_url, "/health", headers)
    models = get_json(args.base_url, "/v1/models", headers)
    voices = get_json(args.base_url, "/v1/audio/voices", headers)
    model_id = first_data_id(models, "/v1/models")
    voice_id = first_data_id(voices, "/v1/audio/voices")

    print(f"health={health.get('status')} model={model_id} voice={voice_id}")

    if not args.speech:
        return

    response = requests.post(
        f"{args.base_url.rstrip('/')}/v1/audio/speech",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "model": model_id,
            "voice": voice_id,
            "input": "你好，这是Neiroha CosyVoice三的语音克隆测试。",
            "response_format": "wav",
        },
        timeout=180,
    )
    response.raise_for_status()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(response.content)
    print(f"speech={args.output} bytes={len(response.content)}")


if __name__ == "__main__":
    main()
