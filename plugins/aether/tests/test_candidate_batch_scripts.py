import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "visual-asset-capture"
TEMPLATE_SCRIPT = SKILL_ROOT / "scripts" / "generate_candidate_template.py"
SAVE_SCRIPT = SKILL_ROOT / "scripts" / "save_candidate_batch.py"


def write_config(root: Path) -> None:
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


class CandidateBatchScriptTests(unittest.TestCase):
    def test_template_script_emits_valid_candidate_batch_without_storage_owned_fields(self):
        result = subprocess.run(
            [
                sys.executable,
                str(TEMPLATE_SCRIPT),
                "--asset-type",
                "lighting",
                "--name",
                "Rainy Neon Reflection",
                "--include-recipe",
                "--include-system",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        asset = payload["candidate_assets"][0]
        self.assertEqual(asset["type"], "lighting")
        self.assertIn("light_source", asset["profile"])
        self.assertNotIn("decision", asset)
        self.assertNotIn("reuse_score", asset)
        self.assertNotIn("target_asset_id", asset)
        self.assertEqual(payload["recipe_candidates"][0]["recipe_assets"][0]["candidate_asset_id"], asset["id"])
        self.assertEqual(payload["visual_system_candidates"][0]["candidate_asset_relations"][0]["candidate_asset_id"], asset["id"])

    def test_save_candidate_batch_script_persists_and_returns_next_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_config(root)
            payload = {
                "candidate_assets": [
                    {
                        "type": "style",
                        "name": "Painterly Test Style",
                        "summary": "soft painterly test style",
                        "status": "draft",
                    }
                ]
            }

            result = subprocess.run(
                [sys.executable, str(SAVE_SCRIPT), "--json", "-", "--summary-only"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(payload),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertTrue(output["batch_id"].startswith("candidate_batch_"))
            self.assertEqual(output["candidate_assets"][0]["evolution_action"], "create_new")
            self.assertIn("aether visual-asset candidates confirm-batch", output["next_commands"][1])


if __name__ == "__main__":
    unittest.main()
