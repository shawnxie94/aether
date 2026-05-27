import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "image-generate" / "scripts" / "record_generation.py"


class RecordGenerationScriptTests(unittest.TestCase):
    def test_retry_metadata_is_written_to_skill_result_meta(self):
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
                "source_prompt": "source",
                "refined_prompt": "refined",
                "negative_prompt": "negative",
                "selected_assets": [{"asset_id": "visual_asset_style-example", "type": "style"}],
                "generation_skill": "rightcodes-imagegen",
                "skill_params": {},
                "skill_result_meta": {"provider": "test"},
                "outputs": [],
                "status": "failed",
                "error": "HTTP 524",
            }

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--json",
                    "-",
                    "--attempt",
                    "2",
                    "--max-attempts",
                    "3",
                    "--retry-of",
                    "generation_previous",
                    "--retryable",
                    "true",
                ],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            retry = output["skill_result_meta"]["retry"]
            self.assertEqual(retry["attempt"], 2)
            self.assertEqual(retry["max_attempts"], 3)
            self.assertEqual(retry["retry_of"], "generation_previous")
            self.assertTrue(retry["retryable"])
            self.assertEqual(output["skill_params"]["aspectRatio"], "1:1")
            self.assertEqual(output["skill_params"]["quality"], "standard")

    def test_prompt_record_generation_params_override_defaults(self):
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
                        },
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "source_prompt": "source",
                "refined_prompt": "refined",
                "generation_skill": "rightcodes-imagegen",
                "prompt_record": {
                    "id": "prompt_1",
                    "generation_params": {"aspectRatio": "9:16"},
                },
                "skill_params": {"quality": "high"},
                "outputs": [str(root / "provider-output.png")],
                "status": "generated",
            }
            (root / "provider-output.png").write_bytes(b"fake png")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", "-"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertEqual(output["skill_params"]["aspectRatio"], "9:16")
            self.assertEqual(output["skill_params"]["quality"], "high")
            self.assertEqual(output["visual_review"]["style_consistency"], "not_reviewed")
            self.assertTrue(output["outputs"][0]["asset_path"].endswith(".png"))
            self.assertIn("assets/generated", output["outputs"][0]["asset_path"])
            self.assertEqual(output["outputs"][0]["original_output"], str(root / "provider-output.png"))

    def test_visual_review_payload_is_preserved(self):
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
                        }
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "source_prompt": "source",
                "refined_prompt": "refined",
                "selected_assets": [{"asset_id": "visual_asset_style-example", "type": "style"}],
                "generation_skill": "imagegen",
                "outputs": [str(root / "generated.png")],
                "status": "generated",
                "visual_review": {
                    "reviewed": True,
                    "style_consistency": "major_deviation",
                    "score": 0.42,
                    "matched_traits": ["soft lighting"],
                    "deviations": ["rendering became photorealistic"],
                    "recommendation": "regenerate",
                    "suggested_revision": "strengthen oil pastel texture",
                },
            }
            (root / "generated.png").write_bytes(b"fake png")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", "-"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertTrue(output["visual_review"]["reviewed"])
            self.assertEqual(output["visual_review"]["style_consistency"], "major_deviation")
            self.assertEqual(output["visual_review"]["recommendation"], "regenerate")
            self.assertIn("assets/generated", output["outputs"][0]["asset_path"])


if __name__ == "__main__":
    unittest.main()
