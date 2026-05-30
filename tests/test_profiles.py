from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
import unittest
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.api.main import create_api_app
from app.gradio_app import build_gradio_admin_blocks
from app.core.profiles import VoiceRegistry, mode_label, normalize_mode_name, profile_mode_name, write_toml_mapping
from app.services.cosyvoice_runtime import SynthesisInput, SynthesisResult
from scripts.download_cosyvoice_assets import MODEL_CATALOG, frontend_resources


class DummyRuntime:
    model_id = "dummy-cosyvoice3"
    model_loaded = False
    sample_rate = 16000

    def synthesize(self, request: SynthesisInput) -> SynthesisResult:
        return SynthesisResult(
            sample_rate=self.sample_rate,
            audio=np.zeros(self.sample_rate // 10, dtype=np.float32),
            elapsed_seconds=0.01,
            audio_seconds=0.1,
            rtf=0.1,
            mode=request.mode,
            voice_name=request.voice_name,
            voice_set=request.voice_set,
            model_preset=request.model_preset,
            voice_id=request.voice_id,
        )


class ProfileTests(unittest.TestCase):
    def test_mode_aliases(self) -> None:
        self.assertEqual(normalize_mode_name("prompt_clone"), "zero_shot")
        self.assertEqual(profile_mode_name("prompt_clone"), "prompt_clone")
        self.assertEqual(normalize_mode_name("零样本复制"), "zero_shot")
        self.assertEqual(normalize_mode_name("cross-lingual"), "cross_lingual")
        self.assertEqual(normalize_mode_name("自然语言控制"), "instruct")
        self.assertEqual(normalize_mode_name("预训练音色"), "sft")
        self.assertEqual(mode_label("prompt_clone"), "语音克隆")

    def test_default_toml_registry_loads_three_clone_modes(self) -> None:
        registry = VoiceRegistry()
        profiles = {profile.id: profile for profile in registry.list_profiles("default")}
        self.assertEqual(set(profiles), {"prompt-clone", "cross-lingual-clone", "instruct-clone"})
        self.assertEqual(profiles["prompt-clone"].mode, "prompt_clone")
        self.assertEqual(profiles["prompt-clone"].engine_mode, "zero_shot")
        self.assertEqual(profiles["cross-lingual-clone"].engine_mode, "cross_lingual")
        self.assertEqual(profiles["instruct-clone"].engine_mode, "instruct")
        self.assertEqual(registry.get_model_preset("cosyvoice3-default").engine, "cosyvoice3")

    def test_legacy_json_registry_still_loads_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voices.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "alice",
                            "name": "Alice",
                            "mode": "zero_shot",
                            "prompt_audio": "ref.wav",
                            "prompt_text": "hello",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry = VoiceRegistry(path)
            profiles = registry.list_profiles()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(registry.get_optional("Alice").id, "alice")
            self.assertEqual(profiles[0].to_speaker_item()["model"], "default")

    def test_openai_models_voices_and_logs(self) -> None:
        registry = VoiceRegistry()
        app = create_api_app(DummyRuntime(), registry, api_url="http://127.0.0.1:19890", admin_url="http://127.0.0.1:17870")
        client = TestClient(app)
        models = client.get("/v1/models")
        self.assertEqual(models.status_code, 200)
        self.assertEqual(models.json()["data"][0]["id"], "default")
        voices = client.get("/v1/audio/voices")
        self.assertEqual(voices.status_code, 200)
        self.assertIn("model_preset", voices.json()["data"][0])
        logs = client.get("/cosyvoice3/logs")
        self.assertEqual(logs.status_code, 200)
        self.assertEqual(logs.json()["name"], "backend.log")
        native_meta = client.get("/api/cosyvoice/meta")
        self.assertEqual(native_meta.status_code, 200)
        self.assertEqual(native_meta.json()["paths"]["native_json"], "/api/cosyvoice/tts")
        native_voices = client.get("/api/cosyvoice/voices")
        self.assertEqual(native_voices.status_code, 200)

    def test_flutter_adapter_contract_routes(self) -> None:
        registry = VoiceRegistry()
        app = create_api_app(DummyRuntime(), registry, api_url="http://127.0.0.1:19890", admin_url="http://127.0.0.1:17870")
        client = TestClient(app)

        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["backend"], "cosyvoice3")

        speakers = client.get("/speakers")
        self.assertEqual(speakers.status_code, 200)
        self.assertIsInstance(speakers.json(), list)
        self.assertIn("name", speakers.json()[0])
        self.assertIn("voice_id", speakers.json()[0])
        self.assertIn("mode", speakers.json()[0])

        profiles = client.get("/cosyvoice/profiles")
        self.assertEqual(profiles.status_code, 200)
        first_profile = profiles.json()["data"][0]
        self.assertIn("id", first_profile)
        self.assertIn("name", first_profile)
        self.assertIn("mode", first_profile)
        self.assertIn("mode_label", first_profile)

        native_speech = client.post(
            "/cosyvoice/speech",
            json={
                "text": "你好",
                "mode": "zero_shot",
                "profile": "prompt-clone",
                "speed": 1.0,
                "response_format": "wav",
                "prompt_lang": "zh",
            },
        )
        self.assertEqual(native_speech.status_code, 200, native_speech.text)
        self.assertEqual(native_speech.headers["content-type"], "audio/wav")

        openai_root_speech = client.post(
            "/audio/speech",
            json={
                "model": "default",
                "voice": "prompt-clone",
                "input": "你好",
                "response_format": "wav",
            },
        )
        self.assertEqual(openai_root_speech.status_code, 200, openai_root_speech.text)
        self.assertEqual(openai_root_speech.headers["content-type"], "audio/wav")

    def test_flutter_adapter_upload_contract_route(self) -> None:
        registry = VoiceRegistry()
        app = create_api_app(DummyRuntime(), registry)
        client = TestClient(app)

        response = client.post(
            "/cosyvoice/speech/upload",
            data={
                "text": "你好",
                "mode": "zero_shot",
                "speed": "1.0",
                "response_format": "wav",
                "prompt_text": "参考文本",
                "prompt_lang": "zh",
            },
            files={"prompt_audio": ("ref.wav", b"placeholder audio", "audio/wav")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "audio/wav")

    def test_chinese_voice_id_uses_header_safe_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_root = root / "configs"
            voices_root = root / "runtime" / "voices"
            ref_audio = root / "ref.wav"
            ref_audio.write_bytes(b"placeholder")
            write_toml_mapping(
                config_root / "server.toml",
                {
                    "api": {"host": "127.0.0.1", "port": 19890, "preload_model": False},
                    "admin": {"enabled": True, "host": "127.0.0.1", "port": 17870},
                    "ui": {"title": "Test", "default_language": "zh"},
                    "runtime": {
                        "active_model_preset": "cosyvoice3-default",
                        "active_voice_set": "default",
                        "default_voice": "中文声音",
                    },
                },
            )
            write_toml_mapping(
                config_root / "model-presets" / "default.toml",
                {
                    "schema_version": 1,
                    "id": "cosyvoice3-default",
                    "name": "Default",
                    "engine": "cosyvoice3",
                    "cosyvoice3": {"model_dir": "models/Fun-CosyVoice3-0.5B"},
                },
            )
            write_toml_mapping(
                config_root / "voice-sets" / "default.toml",
                {
                    "schema_version": 1,
                    "id": "default",
                    "name": "Default",
                    "description": "",
                    "voices": ["中文声音"],
                },
            )
            write_toml_mapping(
                voices_root / "中文声音" / "voice.toml",
                {
                    "schema_version": 1,
                    "id": "中文声音",
                    "name": "中文声音",
                    "mode": "prompt_clone",
                    "model_preset": "cosyvoice3-default",
                    "reference_audio": str(ref_audio),
                    "prompt_text": "参考文本",
                    "text_lang": "zh",
                    "prompt_lang": "zh",
                    "instruction": "",
                    "speed": 1.0,
                    "engine_options": {"speaker_id": "", "speaker_embedding_path": "", "adapter_path": ""},
                },
            )
            registry = VoiceRegistry(root / "missing.json", config_root=config_root, voices_root=voices_root)
            app = create_api_app(DummyRuntime(), registry)
            client = TestClient(app)
            response = client.post(
                "/v1/audio/speech",
                json={"model": "default", "voice": "中文声音", "input": "你好", "response_format": "wav"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["X-Neiroha-Backend"], "cosyvoice3")
            self.assertEqual(response.headers["X-Neiroha-Model-Preset"], "cosyvoice3-default")
            self.assertEqual(response.headers["X-Neiroha-Voice"], urllib.parse.quote("中文声音", safe=""))
            self.assertEqual(response.headers["X-Neiroha-Sample-Rate"], "16000")
            self.assertEqual(response.headers["X-Neiroha-Output-Format"], "wav")
            response.headers["Content-Disposition"].encode("latin-1")
            response.headers["X-Neiroha-Output-Path"].encode("latin-1")
            self.assertIn("runtime/outputs/", response.headers["X-Neiroha-Output-Path"])
            unsupported = client.post(
                "/v1/audio/speech",
                json={"model": "default", "voice": "中文声音", "input": "你好", "response_format": "bad"},
            )
            self.assertEqual(unsupported.status_code, 400)
            self.assertEqual(unsupported.json()["error"]["code"], "unsupported_format")

    def test_gradio_admin_blocks_build_in_zh_and_en(self) -> None:
        registry = VoiceRegistry()
        previous = os.environ.get("NEIROHA_COSYVOICE3_UI_LANG")
        try:
            for language in ("zh", "en"):
                os.environ["NEIROHA_COSYVOICE3_UI_LANG"] = language
                blocks = build_gradio_admin_blocks(
                    api_base="http://127.0.0.1:9",
                    admin_url="http://127.0.0.1:17870",
                    registry=registry,
                )
                self.assertEqual(blocks.__class__.__name__, "Blocks")
        finally:
            if previous is None:
                os.environ.pop("NEIROHA_COSYVOICE3_UI_LANG", None)
            else:
                os.environ["NEIROHA_COSYVOICE3_UI_LANG"] = previous

    def test_windows_auto_frontend_prefetches_wetext(self) -> None:
        self.assertEqual(frontend_resources("auto", system_name="Windows"), ["wetext"])
        self.assertEqual(frontend_resources("auto", system_name="Linux"), ["ttsfrd"])
        self.assertEqual(frontend_resources("both", system_name="Windows"), ["wetext", "ttsfrd"])
        self.assertIn("wetext", MODEL_CATALOG)
        self.assertTrue(MODEL_CATALOG["cosyvoice3"]["with_frontend"])


if __name__ == "__main__":
    unittest.main()
