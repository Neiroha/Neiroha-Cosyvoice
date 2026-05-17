from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.profiles import VoiceRegistry, mode_label, normalize_mode_name


class ProfileTests(unittest.TestCase):
    def test_mode_aliases(self) -> None:
        self.assertEqual(normalize_mode_name("零样本复制"), "zero_shot")
        self.assertEqual(normalize_mode_name("cross-lingual"), "cross_lingual")
        self.assertEqual(normalize_mode_name("自然语言控制"), "instruct")
        self.assertEqual(normalize_mode_name("预训练音色"), "sft")
        self.assertEqual(mode_label("zero_shot"), "语音克隆")

    def test_registry_loads_list(self) -> None:
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
            self.assertEqual(profiles[0].to_speaker_item()["model"], "cosyvoice")


if __name__ == "__main__":
    unittest.main()

