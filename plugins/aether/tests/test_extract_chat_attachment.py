import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "visual-asset-capture" / "scripts" / "extract_chat_attachment.py"


class ExtractChatAttachmentTests(unittest.TestCase):
    def test_script_extracts_data_url_and_ingests_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": "aether.sqlite",
                            "assetRoot": "assets",
                            "referenceImageDir": "assets/references",
                            "generatedImageDir": "assets/generated",
                            "cacheDir": "cache",
                            "runDir": "runs",
                        }
                    }
                ),
                encoding="utf-8",
            )

            codex_home = root / "codex-home"
            session_dir = codex_home / "sessions" / "2026" / "05" / "26"
            session_dir.mkdir(parents=True)
            image_data = base64.b64encode(b"fake image bytes").decode("ascii")
            session_path = session_dir / "rollout-test.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "reference"},
                                {"type": "input_image", "image_url": f"data:image/png;base64,{image_data}"},
                            ],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--session",
                    str(session_path),
                    "--reference-name",
                    "sample-reference",
                ],
                cwd=root,
                env={"CODEX_HOME": str(codex_home)},
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(payload["source_reference"]["original_image_path"], "chat_attachment:sample-reference")
            self.assertEqual(payload["source_reference"]["mime_type"], "image/png")
            self.assertTrue(Path(payload["decoded_path"]).exists())
            self.assertTrue(Path(payload["asset"]["asset_path"]).exists())


if __name__ == "__main__":
    unittest.main()
