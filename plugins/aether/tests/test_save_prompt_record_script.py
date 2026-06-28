import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "prompt-refine" / "scripts" / "save_prompt_record.py"
COMPOSE_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "prompt-refine" / "scripts" / "compose_prompt_record.py"


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
                "selected_assets": [{"asset_id": "visual_asset_style-example", "type": "style"}],
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
            self.assertIn("提示词已经整理好", output["confirmation_message"])
            self.assertIn("complete refined prompt", output["confirmation_message"])
            self.assertIn("complete negative prompt", output["confirmation_message"])
            self.assertIn("画面比例: 16:9", output["confirmation_message"])
            self.assertIn("1. first assumption", output["confirmation_message"])
            self.assertIn("请用户确认", output["confirmation_message"])
            self.assertNotIn("```json", output["confirmation_message"])

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

    def test_emit_confirmation_includes_memory_composition_preview(self):
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
            payload = {
                "source_prompt": "lotus pond key art",
                "selected_assets": [
                    {
                        "asset_id": "visual_asset_internal-style",
                        "type": "style",
                        "name": "Painterly Anime",
                        "reason": "recalled asset score 0.91",
                    },
                    {
                        "asset_id": "visual_asset_internal-palette",
                        "type": "color_palette",
                        "name": "Amber Green",
                    },
                ],
                "composition_plan": {
                    "subject": "lotus pond heroine",
                    "style": "bright painterly anime",
                    "color": "amber and green",
                    "lighting": "soft backlight",
                    "composition": "wide key art",
                    "camera": "slightly elevated view",
                    "mood": ["quiet", "hopeful"],
                    "negative_rules": ["no text overlays"],
                    "recipes": [{"name": "Lotus Key Art Recipe", "reason": "requested recipe"}],
                    "visual_systems": [{"name": "Lotus Pond World", "kind": "worldview"}],
                },
                "refined_prompt": "lotus pond heroine key art",
                "negative_prompt": "no text overlays",
                "conflicts": ["palette conflicts with original monochrome request"],
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
            message = output["confirmation_message"]

            self.assertIn("**记忆组合预览**", message)
            self.assertIn("主体/场景: lotus pond heroine", message)
            self.assertIn("风格: bright painterly anime", message)
            self.assertIn("Recipe / Visual System", message)
            self.assertIn("Lotus Key Art Recipe", message)
            self.assertIn("Lotus Pond World", message)
            self.assertIn("Painterly Anime", message)
            self.assertIn("palette conflicts with original monochrome request", message)
            self.assertNotIn("visual_asset_internal-style", message)

    def test_emit_confirmation_lists_multi_image_prompt_variants(self):
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
            payload = {
                "source_prompt": "three portraits of the same character",
                "refined_prompt": "shared character continuity prompt",
                "negative_prompt": "wrong identity",
                "variants": [
                    {
                        "id": "front_view",
                        "title": "Front View",
                        "refined_prompt": "front view portrait prompt",
                        "negative_prompt": "side view",
                        "generation_params": {"aspectRatio": "3:4"},
                        "composition_plan": {"camera": "front view"},
                        "notes": ["keep identity markers"],
                    },
                    {
                        "id": "side_view",
                        "title": "Side View",
                        "refined_prompt": "side view portrait prompt",
                        "negative_prompt": "front view",
                        "generation_params": {"aspectRatio": "3:4"},
                        "composition_plan": {"camera": "side view"},
                    },
                ],
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

            self.assertEqual(len(output["record"]["variants"]), 2)
            self.assertIn("**多图版本**", output["confirmation_message"])
            self.assertIn("Front View", output["confirmation_message"])
            self.assertIn("front view portrait prompt", output["confirmation_message"])
            self.assertIn("Side View", output["confirmation_message"])
            self.assertIn("请用户确认这些版本", output["confirmation_message"])

    def test_compose_prompt_record_script_saves_and_emits_confirmation(self):
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
                            "defaultGenerationSkill": "imagegen",
                            "defaultParams": {
                                "aspectRatio": "1:1",
                                "quality": "standard",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            overlay = {
                "refined_prompt": "polished misty forest prompt",
                "negative_prompt": "low detail",
                "assumptions": ["kept the subject broad"],
            }

            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPOSE_SCRIPT),
                    "--source-prompt",
                    "misty forest",
                    "--overlay-json",
                    "-",
                    "--save",
                    "--emit-confirmation",
                ],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                input=json.dumps(overlay),
                check=True,
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)

            self.assertTrue(output["record"]["id"].startswith("prompt_"))
            self.assertEqual(output["record"]["refined_prompt"], "polished misty forest prompt")
            self.assertEqual(output["record"]["generation_params"]["aspectRatio"], "1:1")
            self.assertIn("polished misty forest prompt", output["confirmation_message"])


    def test_model_emitted_intent_sketch_persists_to_prompt_records(self):
        """When Codex emits a structured intent_sketch, the saved prompt
        record must persist it verbatim. This pins down the contract from
        skills/prompt-refine/SKILL.md step 4, which now requires the model
        to emit a populated intent_sketch in the same pass as refined_prompt.
        """
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
                            "defaultParams": {"aspectRatio": "1:1", "quality": "standard"}
                        },
                    }
                ),
                encoding="utf-8",
            )
            # Codex now emits the populated intent_sketch in the same pass
            # that produces the final refined_prompt. The save script should
            # accept it and persist it without filtering the model input.
            intent_sketch = {
                "subject": "an elderly clockmaker in a dusty workshop",
                "scene": "evening, lit by a single warm bulb",
                "action": "polishing a brass gear",
                "mood": ["contemplative", "warm"],
                "style_intent": ["oil painting"],
                "composition_intent": ["medium shot", "shallow depth of field"],
                "color_lighting_intent": ["amber", "low key"],
                "negative_intent": ["modern technology"],
                "user_constraints": ["no text overlays"],
                "assumptions": ["era implied to be early 20th century"],
                "output_format": "single",
                "requested_count": 1,
            }
            payload = {
                "source_prompt": "an elderly clockmaker polishing a brass gear at sunset",
                "refined_prompt": "Oil painting of an elderly clockmaker polishing a brass gear at sunset, warm amber light.",
                "negative_prompt": "modern technology, text overlays",
                "intent_sketch": intent_sketch,
                "generation_params": {"aspectRatio": "4:3"},
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
            record = json.loads(result.stdout)

            # The persisted record must carry the model-produced intent_sketch
            # verbatim — no field filtering, no fallback to the empty
            # placeholder that the compose step produces.
            self.assertEqual(record["intent_sketch"], intent_sketch)
            self.assertEqual(record["intent_sketch"]["subject"], intent_sketch["subject"])
            self.assertEqual(record["intent_sketch"]["mood"], ["contemplative", "warm"])
            self.assertEqual(record["intent_sketch"]["output_format"], "single")
            # The legacy compose-time placeholder fields must NOT leak in
            # once the model has provided real values.
            self.assertNotEqual(record["intent_sketch"].get("query_terms"), [])


if __name__ == "__main__":
    unittest.main()
