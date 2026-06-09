import unittest

from aether_core.validation import (
    ValidationError,
    validate_recipe_candidate,
    validate_recipe,
    validate_visual_system_candidate,
    validate_generation_run,
    validate_prompt_record,
    validate_visual_asset,
    validate_visual_asset_candidate,
)


class ValidationTests(unittest.TestCase):
    def test_prompt_requires_refined_prompt(self):
        with self.assertRaises(ValidationError):
            validate_prompt_record({"source_prompt": "x"})

    def test_visual_asset_requires_known_type(self):
        with self.assertRaises(ValidationError):
            validate_visual_asset({"type": "unknown", "name": "x"})

    def test_visual_asset_list_fields_must_be_lists(self):
        with self.assertRaises(ValidationError):
            validate_visual_asset({"type": "lighting", "name": "x", "prompt_fragments": "soft light"})

    def test_visual_asset_candidate_batch_validates_items(self):
        with self.assertRaises(ValidationError):
            validate_visual_asset_candidate({"candidate_assets": [{"type": "unknown", "name": "x"}]})

    def test_database_semantic_fields_must_be_english(self):
        with self.assertRaisesRegex(ValidationError, "must use English"):
            validate_visual_asset(
                {
                    "type": "style",
                    "name": "东方幻想厚涂风",
                }
            )
        with self.assertRaisesRegex(ValidationError, "must use English"):
            validate_visual_asset_candidate(
                {
                    "type": "color_palette",
                    "name": "Warm Fantasy Palette",
                    "prompt_fragments": ["金色树冠"],
                }
            )
        with self.assertRaisesRegex(ValidationError, "must use English"):
            validate_recipe_candidate(
                {
                    "name": "Forest Key Art",
                    "composition_rules": [
                        {
                            "key": "asset_roles",
                            "value": ["使用绿色灵光"],
                        }
                    ],
                }
            )
        with self.assertRaisesRegex(ValidationError, "must use English"):
            validate_visual_system_candidate(
                {
                    "kind": "art_direction",
                    "name": "Bioluminescent Canopy Direction",
                    "visual_rules": [
                        {
                            "key": "subject_aesthetic",
                            "value": ["巨型有机天穹"],
                        }
                    ],
                }
            )

    def test_source_reference_text_may_preserve_original_language(self):
        validate_visual_asset_candidate(
            {
                "type": "style",
                "name": "Painterly Fantasy Canopy",
                "summary": "Loose painterly fantasy canopy style.",
                "source_references": [
                    {
                        "asset_id": "asset_reference",
                        "image_path": "/tmp/reference.png",
                        "user_note": "用户上传的参考图",
                        "source_prompt": "东方幻想森林",
                    }
                ],
            }
        )

    def test_visual_asset_candidate_analysis_evidence_validates_shape(self):
        validate_visual_asset_candidate(
            {
                "type": "lighting",
                "name": "Backlit Mist Edge",
                "analysis_observations": [
                    {
                        "trait": "soft rim light on mist edges",
                        "evidence": "bright edge glow around the foreground silhouette",
                        "region": "foreground edge",
                        "source": "visual_observation",
                        "confidence": 0.82,
                        "reusable": True,
                    }
                ],
                "excluded_observations": [
                    {
                        "trait": "temporary object count",
                        "evidence": "three visible lamps are source-specific",
                        "source": "visual_observation",
                        "confidence": 0.7,
                        "reusable": False,
                    }
                ],
                "consensus": {
                    "reference_count": 3,
                    "appears_in": 2,
                    "consensus_strength": 0.67,
                    "common_traits": ["soft rim light"],
                    "variant_traits": ["warmer edge glow"],
                    "outlier_traits": ["hard spotlight"],
                },
            }
        )
        with self.assertRaisesRegex(ValidationError, "source must be one of"):
            validate_visual_asset_candidate(
                {
                    "type": "lighting",
                    "name": "Bad Source",
                    "analysis_observations": [{"trait": "rim light", "source": "guessed"}],
                }
            )

    def test_active_visual_asset_rejects_unresolved_chat_attachment_reference(self):
        with self.assertRaisesRegex(ValidationError, "unresolved chat_attachment"):
            validate_visual_asset(
                {
                    "type": "style",
                    "name": "Soft Pencil Portrait",
                    "status": "active",
                    "source_references": [
                        {
                            "original_image_path": "chat_attachment:soft-pencil-reference",
                            "role": "positive_reference",
                        }
                    ],
                }
            )

    def test_active_recipe_rejects_chat_attachment_source_reference_ids(self):
        with self.assertRaisesRegex(ValidationError, "chat_attachment source_reference_ids"):
            validate_recipe(
                {
                    "name": "Soft Pencil Portrait Recipe",
                    "status": "active",
                    "source_reference_ids": ["chat_attachment:soft-pencil-reference"],
                }
            )

    def test_prompt_generation_params_must_be_object(self):
        with self.assertRaises(ValidationError):
            validate_prompt_record(
                {
                    "source_prompt": "x",
                    "refined_prompt": "y",
                    "generation_params": "16:9",
                }
            )

    def test_generation_requires_skill(self):
        with self.assertRaises(ValidationError):
            validate_generation_run({"refined_prompt": "x"})

    def test_generation_visual_review_must_be_object(self):
        with self.assertRaises(ValidationError):
            validate_generation_run(
                {
                    "refined_prompt": "x",
                    "generation_skill": "imagegen",
                    "visual_review": "pass",
                }
            )

    def test_generation_edit_regions_must_be_list(self):
        with self.assertRaises(ValidationError):
            validate_generation_run(
                {
                    "refined_prompt": "x",
                    "generation_skill": "imagegen",
                    "mode": "edit",
                    "edit_regions": {"label": "hand"},
                }
            )


if __name__ == "__main__":
    unittest.main()
