import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aether_core.storage import AetherStore


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "image-generate" / "scripts" / "record_generation.py"
ATTEMPTS_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "image-generate" / "scripts" / "record_generation_attempts.py"


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

    def test_successful_generation_adds_reuse_suggestion_message(self):
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
                    }
                ),
                encoding="utf-8",
            )
            store = AetherStore(root / "aether.sqlite")
            store.init()
            scene = store.create_visual_asset(
                {"type": "scene", "name": "Lotus Pond", "summary": "lotus pond world", "status": "active"}
            )
            style = store.create_visual_asset(
                {"type": "style", "name": "Painterly Anime", "summary": "bright painterly anime", "status": "active"}
            )
            palette = store.create_visual_asset(
                {"type": "color_palette", "name": "Amber Green", "summary": "amber and green", "status": "active"}
            )
            output_path = root / "lotus.png"
            output_path.write_bytes(b"fake png")
            payload = {
                "source_prompt": "lotus pond key art",
                "refined_prompt": "lotus pond key art",
                "selected_assets": [
                    {"asset_id": scene["id"], "type": "scene"},
                    {"asset_id": style["id"], "type": "style"},
                    {"asset_id": palette["id"], "type": "color_palette"},
                ],
                "generation_skill": "imagegen",
                "skill_params": {"aspectRatio": "16:9"},
                "status": "generated",
                "visual_review": {
                    "reviewed": True,
                    "style_consistency": "high",
                    "score": 0.92,
                    "recipe_fidelity": "high",
                    "subject_consistency": "high",
                },
                "outputs": [str(output_path)],
            }

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
            message = output["reuse_suggestion_message"]

            self.assertIn("reuse_suggestions", output)
            self.assertIn("这次生成已经形成可复用沉淀候选", message)
            self.assertIn("Recipe（组合方式）", message)
            self.assertIn("Visual System（整体视觉系统）", message)
            self.assertIn("Generated Recipe", message)
            self.assertIn("Generated System", message)
            self.assertIn("不会自动写入长期记忆", message)

    def test_edit_record_preserves_source_lineage(self):
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
                "mode": "edit",
                "source_generation_id": "generation_parent",
                "source_output_asset_id": "asset_source",
                "edit_instruction": "Fix only the sign text and preserve the rest.",
                "edit_regions": [{"label": "sign", "issue": "garbled text"}],
                "source_prompt": "rainy storefront",
                "refined_prompt": "rainy storefront, corrected sign text",
                "generation_skill": "imagegen",
                "outputs": [str(root / "edited.png")],
                "status": "edited",
            }
            (root / "edited.png").write_bytes(b"fake png")

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

            self.assertEqual(output["mode"], "edit")
            self.assertEqual(output["source_generation_id"], "generation_parent")
            self.assertEqual(output["source_output_asset_id"], "asset_source")
            self.assertEqual(output["edit_regions"][0]["label"], "sign")
            self.assertEqual(output["visual_review"]["style_consistency"], "not_reviewed")
            self.assertIn("assets/generated", output["outputs"][0]["asset_path"])

    def test_attempt_manifest_records_attempts_and_chains_retry_ids(self):
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
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "success.png").write_bytes(b"fake png")
            manifest = {
                "request_id": "request_1",
                "max_attempts": 2,
                "attempts": [
                    {
                        "source_prompt": "source",
                        "refined_prompt": "refined",
                        "generation_skill": "imagegen",
                        "outputs": [],
                        "status": "failed",
                        "error": "HTTP 524",
                        "retryable": True,
                    },
                    {
                        "source_prompt": "source",
                        "refined_prompt": "refined",
                        "generation_skill": "imagegen",
                        "outputs": [str(root / "success.png")],
                        "status": "generated",
                        "retryable": False,
                    },
                ],
            }

            result = subprocess.run(
                [sys.executable, str(ATTEMPTS_SCRIPT), "--manifest", "-"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(manifest),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertEqual(len(output["records"]), 2)
            first, second = output["records"]
            self.assertEqual(first["skill_result_meta"]["retry"]["attempt"], 1)
            self.assertEqual(first["skill_result_meta"]["retry"]["request_id"], "request_1")
            self.assertTrue(first["skill_result_meta"]["retry"]["retryable"])
            self.assertEqual(second["skill_result_meta"]["retry"]["retry_of"], first["id"])
            self.assertEqual(output["final_record"]["status"], "generated")
            self.assertIn("assets/generated", second["outputs"][0]["asset_path"])


if __name__ == "__main__":
    unittest.main()
