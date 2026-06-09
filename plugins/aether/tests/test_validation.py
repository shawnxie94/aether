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


    def test_recipe_accepts_must_cover_ratios_and_signature_self_check_keys(self):
        from aether_core.validation import validate_recipe, COMPOSITION_RULE_KEYS
        self.assertIn("must_cover_ratios", COMPOSITION_RULE_KEYS)
        self.assertIn("signature_self_check", COMPOSITION_RULE_KEYS)
        payload = {
            "name": "Soft Blue Pencil Shoujo Portrait Recipe",
            "summary": "Test recipe with signature coverage rules.",
            "use_cases": ["portrait"],
            "composition_rules": [
                {
                    "key": "must_cover_ratios",
                    "value": [
                        "powder blue covers at least 35% of the upper frame",
                        "warm paper negative space covers at least 30%",
                    ],
                    "reason": "Recipe signature coverage budgets.",
                },
                {
                    "key": "signature_self_check",
                    "value": [
                        "iris shows visible coral-red and deep-blue split, not just highlights",
                        "sailor collar or ruffled camisole anchors the lower frame",
                    ],
                    "reason": "Anchors the model against word-frequency drift.",
                },
                {
                    "key": "negative_constraints",
                    "value": ["no glossy 3d render"],
                },
            ],
        }
        validate_recipe(payload)

    def test_recipe_rejects_unknown_composition_rule_key(self):
        from aether_core.validation import validate_recipe
        payload = {
            "name": "Bad Recipe",
            "summary": "Has unknown key.",
            "use_cases": ["x"],
            "composition_rules": [
                {"key": "made_up_key", "value": ["x"]},
            ],
        }
        with self.assertRaises(Exception) as ctx:
            validate_recipe(payload)
        self.assertIn("composition_rules.key", str(ctx.exception))

    def test_visual_review_accepts_fidelity_breakdown(self):
        from aether_core.validation import validate_visual_review
        review = {
            "reviewed": True,
            "style_consistency": "moderate",
            "score": 0.7,
            "recipe_fidelity": "moderate",
            "recipe_fidelity_score": 0.65,
            "subject_consistency": "high",
            "subject_consistency_score": 0.9,
            "matched_traits": ["a"],
            "matched_signature_traits": ["powder blue iris"],
            "matched_subject_traits": ["white cat hairclip"],
            "deviations": ["red-blue iris lost"],
            "recommendation": "regenerate",
        }
        validate_visual_review(review)

    def test_visual_review_accepts_legacy_pass_value(self):
        from aether_core.validation import validate_visual_review
        validate_visual_review({
            "reviewed": True,
            "style_consistency": "pass",
            "score": 0.9,
        })

    def test_visual_review_rejects_invalid_fidelity_value(self):
        from aether_core.validation import validate_visual_review
        with self.assertRaises(Exception) as ctx:
            validate_visual_review({
                "reviewed": True,
                "recipe_fidelity": "some_unsupported_value",
            })
        self.assertIn("recipe_fidelity", str(ctx.exception))

    def test_visual_review_rejects_non_bool_reviewed(self):
        from aether_core.validation import validate_visual_review
        with self.assertRaises(Exception) as ctx:
            validate_visual_review({"reviewed": "yes"})
        self.assertIn("reviewed", str(ctx.exception))

    def test_visual_review_rejects_invalid_style_consistency_value(self):
        from aether_core.validation import validate_visual_review
        with self.assertRaises(Exception) as ctx:
            validate_visual_review({
                "reviewed": True,
                "style_consistency": "not_a_real_value",
            })
        self.assertIn("style_consistency", str(ctx.exception))


    def test_visual_review_records_infra_error_on_failure(self):
        # The failure path must still leave an auditable visual_review
        # record so retry history is inspectable.
        from aether_core.validation import validate_visual_review
        review = {
            "reviewed": False,
            "style_consistency": "not_reviewed",
            "score": None,
            "recipe_fidelity": "not_reviewed",
            "recipe_fidelity_score": None,
            "subject_consistency": "not_reviewed",
            "subject_consistency_score": None,
            "matched_traits": [],
            "matched_signature_traits": [],
            "matched_subject_traits": [],
            "deviations": ["infra error: provider returned excessive system load"],
            "recommendation": "use",
            "suggested_revision": "",
            "suggested_edit_instruction": "",
            "localized_deviations": [],
        }
        validate_visual_review(review)


if __name__ == "__main__":
    unittest.main()
