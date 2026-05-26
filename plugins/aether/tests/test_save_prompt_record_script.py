import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "prompt-refine" / "scripts" / "save_prompt_record.py"


class SavePromptRecordScriptTests(unittest.TestCase):
    def test_emit_confirmation_includes_complete_prompt_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": "aether.sqlite",
                            "assetRoot": "assets",
                            "referenceImageDir": "assets/references",
                            "generatedImageDir": "assets/generated",
                            "cacheDir": "cache",
                            "runDir": "runs",
                        },
                        "generation": {
                            "defaultParams": {
                                "aspectRatio": "1:1",
                                "quality": "standard",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "source_prompt": "cute character",
                "style_id": "style_example",
                "target_generation_skill": "rightcodes-imagegen",
                "refined_prompt": "complete refined prompt",
                "negative_prompt": "complete negative prompt",
                "generation_params": {"aspectRatio": "16:9"},
                "assumptions": ["first assumption", "second assumption"],
            }

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", "-", "--emit-confirmation"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertEqual(output["record"]["refined_prompt"], "complete refined prompt")
            self.assertEqual(output["record"]["generation_params"]["aspectRatio"], "16:9")
            self.assertEqual(output["record"]["generation_params"]["quality"], "standard")
            self.assertIn("complete refined prompt", output["confirmation_message"])
            self.assertIn("complete negative prompt", output["confirmation_message"])
            self.assertIn('"aspectRatio": "16:9"', output["confirmation_message"])
            self.assertIn("1. first assumption", output["confirmation_message"])
            self.assertIn("Ask the user to confirm", output["confirmation_message"])

    def test_emit_confirmation_adds_default_generation_params(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": "aether.sqlite",
                            "assetRoot": "assets",
                            "referenceImageDir": "assets/references",
                            "generatedImageDir": "assets/generated",
                            "cacheDir": "cache",
                            "runDir": "runs",
                        },
                        "generation": {
                            "defaultParams": {
                                "aspectRatio": "3:4",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "source_prompt": "portrait",
                "refined_prompt": "portrait refined",
            }

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", "-", "--emit-confirmation"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertEqual(output["record"]["generation_params"]["aspectRatio"], "3:4")


if __name__ == "__main__":
    unittest.main()
