import sys
import tempfile
import unittest
from pathlib import Path

from aether_core.storage import AetherStore
from aether_core.validation import ValidationError


class StorageTests(unittest.TestCase):
    def test_visual_asset_prompt_generation_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            visual_asset = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Neon Melancholy",
                    "summary": "lonely neon city style",
                    "tags": ["neon", "cinematic"],
                    "status": "active",
                    "profile": {
                        "medium": "cinematic photo",
                        "rendering": "cyberpunk",
                    },
                }
            )

            self.assertEqual(visual_asset["status"], "active")
            self.assertEqual(len(store.list_visual_assets()), 1)
            self.assertEqual(store.get_visual_asset(visual_asset["id"])["name"], "Neon Melancholy")

            prompt = store.save_prompt_record(
                {
                    "source_prompt": "lonely girl in future city",
                    "selected_assets": [
                        {"asset_id": visual_asset["id"], "type": "style"}
                    ],
                    "refined_prompt": "cinematic neon lonely girl in future city",
                    "negative_prompt": "flat lighting",
                    "generation_params": {"aspectRatio": "16:9"},
                }
            )
            self.assertTrue(prompt["id"].startswith("prompt_"))
            self.assertEqual(prompt["selected_assets"][0]["asset_id"], visual_asset["id"])
            self.assertEqual(prompt["generation_params"]["aspectRatio"], "16:9")

            generation = store.create_generation_run(
                {
                    "source_prompt": "lonely girl in future city",
                    "refined_prompt": prompt["refined_prompt"],
                    "selected_assets": prompt["selected_assets"],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "visual_review": {
                        "reviewed": True,
                        "style_consistency": "pass",
                        "score": 0.9,
                    },
                    "outputs": ["generated.png"],
                }
            )
            updated = store.update_generation_feedback(
                generation["id"], {"liked": True, "notes": "works"}, "liked"
            )

            self.assertEqual(updated["status"], "liked")
            self.assertTrue(updated["feedback"]["liked"])
            self.assertEqual(updated["visual_review"]["style_consistency"], "pass")

            archived = store.update_visual_asset_status(visual_asset["id"], "archived")
            self.assertEqual(archived["status"], "archived")

            asset = store.create_asset(
                {
                    "kind": "reference",
                    "source_path": "/tmp/source.png",
                    "asset_path": "/tmp/asset.png",
                    "sha256": "abc",
                    "mime_type": "image/png",
                    "size_bytes": 12,
                }
            )
            self.assertTrue(asset["id"].startswith("asset_"))

    def test_generation_list_get_and_stats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            first = store.create_generation_run(
                {
                    "source_prompt": "source one",
                    "refined_prompt": "refined one",
                    "selected_assets": [
                        {"asset_id": "visual_asset_style-a", "type": "style"}
                    ],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "visual_review": {
                        "style_consistency": "major_deviation",
                        "score": 0.4,
                        "deviations": ["lost texture", "wrong palette"],
                    },
                    "outputs": [{"image_path": "/tmp/one.png"}],
                }
            )
            second = store.create_generation_run(
                {
                    "source_prompt": "source two",
                    "refined_prompt": "refined two",
                    "selected_assets": [
                        {"asset_id": "visual_asset_style-a", "type": "style"}
                    ],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "visual_review": {
                        "style_consistency": "pass",
                        "score": 0.9,
                    },
                    "outputs": [{"image_path": "/tmp/two.png"}],
                }
            )
            store.update_generation_feedback(second["id"], {"liked": True}, "liked")

            self.assertEqual(store.get_generation_run(first["id"])["id"], first["id"])
            self.assertEqual(len(store.list_generation_runs(asset_id="visual_asset_style-a")), 2)
            self.assertEqual(len(store.list_generation_runs(review="major_deviation")), 1)
            self.assertEqual(store.list_generation_runs(status="liked")[0]["id"], second["id"])

            stats = store.generation_stats(asset_id="visual_asset_style-a")
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["by_review"]["major_deviation"], 1)
            self.assertEqual(stats["by_review"]["pass"], 1)
            self.assertEqual(stats["feedback"]["liked"], 1)
            self.assertEqual(stats["by_asset"]["visual_asset_style-a"]["total"], 2)
            self.assertEqual(stats["common_deviations"][0]["deviation"], "lost texture")

    def test_generation_edit_lineage_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            original = store.create_generation_run(
                {
                    "source_prompt": "portrait",
                    "refined_prompt": "soft portrait",
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "outputs": [{"asset_id": "asset_original", "image_path": "/tmp/original.png"}],
                }
            )
            edited = store.create_generation_run(
                {
                    "mode": "edit",
                    "source_generation_id": original["id"],
                    "source_output_asset_id": "asset_original",
                    "edit_instruction": "Fix only the right hand and preserve the face.",
                    "edit_regions": [{"label": "right hand", "issue": "extra fingers"}],
                    "source_prompt": "portrait",
                    "refined_prompt": "soft portrait, corrected right hand",
                    "generation_skill": "imagegen",
                    "status": "edited",
                    "visual_review": {
                        "style_consistency": "minor_deviation",
                        "localized_deviations": ["right hand needed repair"],
                        "recommendation": "use",
                    },
                    "outputs": [{"asset_id": "asset_edit", "image_path": "/tmp/edit.png"}],
                }
            )

            loaded = store.get_generation_run(edited["id"])
            self.assertEqual(loaded["mode"], "edit")
            self.assertEqual(loaded["source_generation_id"], original["id"])
            self.assertEqual(loaded["source_output_asset_id"], "asset_original")
            self.assertEqual(loaded["edit_regions"][0]["label"], "right hand")
            self.assertEqual(store.list_generation_runs(status="edited")[0]["id"], edited["id"])

    def test_visual_asset_lifecycle_and_search(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            asset = store.create_visual_asset(
                {
                    "type": "lighting",
                    "name": "Rainy Neon Reflection",
                    "summary": "neon reflections on wet asphalt",
                    "tags": ["neon", "rain"],
                    "profile": {"light_source": "neon signage"},
                    "prompt_fragments": ["rain-soaked asphalt reflections"],
                    "negative_fragments": ["flat lighting"],
                    "recommended_aspect_ratios": ["16:9"],
                    "status": "draft",
                }
            )
            self.assertTrue(asset["id"].startswith("visual_asset_"))
            self.assertEqual(store.get_visual_asset(asset["id"])["name"], "Rainy Neon Reflection")

            with self.assertRaises(ValidationError):
                store.create_visual_asset(
                    {
                        "type": "lighting",
                        "name": "Invalid Lighting Profile",
                        "profile": {"medium": "watercolor"},
                    }
                )

            active = store.update_visual_asset_status(asset["id"], "active")
            self.assertEqual(active["status"], "active")
            self.assertEqual(len(store.list_visual_assets(asset_type="lighting", status="active")), 1)
            self.assertEqual(len(store.list_visual_assets(tag="neon")), 1)
            self.assertEqual(len(store.list_visual_assets(query="asphalt")), 1)

            branch = store.branch_visual_asset(
                asset["id"],
                {
                    "type": "lighting",
                    "name": "Rainy Neon Reflection Variant",
                    "summary": "warmer neon reflections",
                },
            )
            self.assertEqual(branch["parent_asset_id"], asset["id"])

            merged = store.merge_visual_asset(branch["id"], asset["id"])
            self.assertEqual(merged["status"], "merged")
            self.assertEqual(merged["merged_into_asset_id"], asset["id"])

    def test_candidate_confirmation_and_evidence_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            existing = store.create_visual_asset(
                {
                    "type": "lighting",
                    "name": "Rainy Neon Reflection",
                    "summary": "neon reflections on wet asphalt",
                    "tags": ["neon", "rain"],
                    "prompt_fragments": ["rain-soaked asphalt reflections"],
                    "status": "active",
                }
            )
            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "type": "lighting",
                            "name": "Rainy Neon Reflection Variant",
                            "summary": "rainy neon asphalt reflection",
                            "tags": ["neon", "rain"],
                            "prompt_fragments": ["wet asphalt neon reflections"],
                        }
                    ]
                }
            )
            candidate = batch["candidate_assets"][0]
            self.assertEqual(candidate["batch_id"], batch["batch_id"])
            self.assertTrue(candidate["similar_candidates"])

            decided = store.decide_visual_asset_candidate(
                candidate["id"],
                "asset_variant",
                target_asset_id=existing["id"],
            )
            self.assertEqual(decided["status"], "confirmed")
            confirmed = store.get_visual_asset(decided["confirmed_asset_id"])
            self.assertEqual(confirmed["parent_asset_id"], existing["id"])

            run = store.create_generation_run(
                {
                    "source_prompt": "rain city",
                    "refined_prompt": "rain city with wet neon",
                    "selected_assets": [{"asset_id": existing["id"], "type": "lighting"}],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "visual_review": {"style_consistency": "pass", "score": 0.9},
                    "outputs": [{"image_path": "/tmp/neon.png"}],
                }
            )
            store.update_generation_feedback(run["id"], {"liked": True}, "liked")
            evidence_types = {
                item["evidence_type"]
                for item in store.list_visual_asset_evidence(asset_id=existing["id"], limit=None)
            }
            self.assertIn("generated_success", evidence_types)
            self.assertIn("review", evidence_types)
            self.assertIn("user_feedback", evidence_types)
            self.assertGreater(store.visual_asset_quality(existing["id"])["score"], 0.7)

    def test_visual_system_recipe_and_candidate_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Oil Pastel Anime",
                    "summary": "hand drawn oil pastel anime",
                    "status": "active",
                }
            )
            texture = store.create_visual_asset(
                {
                    "type": "texture",
                    "name": "Paper Grain",
                    "summary": "off white grainy paper",
                    "status": "active",
                }
            )

            system = store.create_visual_system(
                {
                    "kind": "genre",
                    "name": "Oil Pastel Daily Anime",
                    "summary": "handmade anime illustration system",
                    "visual_rules": [
                        {"key": "rendering_expectations", "value": ["preserve tactile paper"]},
                    ],
                    "assets": [
                        {
                            "asset_id": style["id"],
                            "role": "core",
                            "weight": 0.9,
                            "reason": "core style",
                        },
                        {
                            "asset_id": texture["id"],
                            "role": "optional",
                            "weight": 0.7,
                        },
                    ],
                    "status": "active",
                }
            )
            self.assertEqual(system["kind"], "genre")
            self.assertEqual(len(store.get_visual_system(system["id"])["assets"]), 2)

            recipe = store.create_recipe(
                {
                    "name": "Oil Pastel Character",
                    "parent_system_ids": [system["id"]],
                    "required_asset_types": ["style", "texture"],
                    "composition_rules": [
                        {
                            "key": "style_application",
                            "value": ["apply oil pastel style over paper grain"],
                            "reason": "style and texture must stay bound",
                        }
                    ],
                    "recommended_aspect_ratios": ["4:3"],
                    "assets": [
                        {
                            "asset_id": style["id"],
                            "role": "core",
                            "weight": 0.9,
                        },
                        {
                            "asset_id": texture["id"],
                            "role": "core",
                            "weight": 0.8,
                        },
                    ],
                    "status": "active",
                }
            )
            self.assertEqual(store.list_recipes(system_id=system["id"])[0]["id"], recipe["id"])
            self.assertEqual(recipe["composition_rules"][0]["key"], "style_application")
            self.assertEqual(len(store.get_recipe(recipe["id"])["assets"]), 2)

            with self.assertRaises(ValidationError):
                store.create_recipe(
                    {
                        "name": "Invalid Rule Recipe",
                        "composition_rules": [{"key": "medium", "value": ["not a recipe rule"]}],
                    }
                )

            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "id": "candidate_style",
                            "type": "style",
                            "name": "Loose Gouache Fantasy",
                            "summary": "bright loose fantasy painting",
                            "asset_status": "active",
                        }
                    ],
                    "recipe_candidates": [
                        {
                            "name": "Fantasy Source Recipe",
                            "required_asset_types": ["style"],
                            "composition_rules": [
                                {
                                    "key": "asset_roles",
                                    "value": ["style: Loose Gouache Fantasy"],
                                }
                            ],
                            "recipe_assets": [
                                {
                                    "candidate_asset_id": "candidate_style",
                                    "role": "core",
                                    "weight": 0.8,
                                }
                            ],
                            "confidence": 0.65,
                            "source": "same_reference_image",
                        }
                    ],
                }
            )
            asset_candidate = batch["candidate_assets"][0]
            recipe_candidate = batch["recipe_candidates"][0]
            decided = store.decide_visual_asset_candidate(asset_candidate["id"], "new_asset")
            confirmed = store.confirm_recipe_candidate(recipe_candidate["id"])
            self.assertEqual(confirmed["status"], "confirmed")
            confirmed_recipe = confirmed["recipe"]
            self.assertEqual(confirmed_recipe["assets"][0]["asset_id"], decided["confirmed_asset_id"])
            self.assertEqual(confirmed_recipe["assets"][0]["role"], "core")
            self.assertEqual(confirmed_recipe["composition_rules"][0]["key"], "asset_roles")

    def test_candidate_ignore_delete_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "id": "candidate_palette",
                            "type": "color_palette",
                            "name": "Unused Palette",
                            "summary": "temporary palette",
                        }
                    ],
                    "recipe_candidates": [{"id": "recipe_candidate_unused", "name": "Unused Recipe"}],
                    "visual_system_candidates": [
                        {
                            "id": "system_candidate_unused",
                            "kind": "art_direction",
                            "name": "Unused System",
                        }
                    ],
                }
            )

            self.assertEqual(store.ignore_visual_asset_candidate("candidate_palette")["status"], "ignored")
            self.assertEqual(store.ignore_recipe_candidate("recipe_candidate_unused")["status"], "ignored")
            self.assertEqual(store.ignore_visual_system_candidate("system_candidate_unused")["status"], "ignored")

            self.assertEqual(store.cleanup_visual_asset_candidates(batch_id=batch["batch_id"])["deleted_count"], 1)
            self.assertEqual(store.cleanup_recipe_candidates(batch_id=batch["batch_id"])["deleted_count"], 1)
            self.assertEqual(store.cleanup_visual_system_candidates(batch_id=batch["batch_id"])["deleted_count"], 1)
            self.assertIsNone(store.get_visual_asset_candidate("candidate_palette"))
            self.assertIsNone(store.get_recipe_candidate("recipe_candidate_unused"))
            self.assertIsNone(store.get_visual_system_candidate("system_candidate_unused"))

            pending = store.create_visual_system_candidate(
                {"id": "system_candidate_pending", "kind": "art_direction", "name": "Pending System"}
            )
            self.assertEqual(store.delete_visual_system_candidate(pending["id"])["id"], pending["id"])
            self.assertIsNone(store.get_visual_system_candidate(pending["id"]))

            confirmed = store.create_visual_system_candidate(
                {"id": "system_candidate_confirmed", "kind": "art_direction", "name": "Confirmed System"}
            )
            store.confirm_visual_system_candidate(confirmed["id"])
            with self.assertRaises(ValueError):
                store.delete_visual_system_candidate(confirmed["id"])

    def test_auto_recipe_slug_uses_unique_suffix_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            first = store.create_recipe(
                {
                    "name": "Source Image Recipe",
                    "summary": "first recipe",
                    "status": "active",
                }
            )
            second = store.create_recipe(
                {
                    "name": "Source Image Recipe",
                    "summary": "second recipe",
                    "status": "draft",
                }
            )

            self.assertEqual(first["id"], "recipe_source-image-recipe")
            self.assertEqual(second["id"], "recipe_source-image-recipe-2")
            self.assertEqual(store.get_recipe(first["id"])["summary"], "first recipe")
            self.assertEqual(store.get_recipe(second["id"])["summary"], "second recipe")

    def test_visual_system_candidate_suggestion_and_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            existing = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Bright Lotus Anime",
                    "summary": "bright lotus pond anime key art",
                    "tags": ["lotus", "anime"],
                    "status": "active",
                }
            )

            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "id": "candidate_scene",
                            "type": "scene",
                            "name": "Lotus Pond Garden",
                            "summary": "bright lotus pond with koi and stone platforms",
                            "tags": ["lotus", "pond"],
                            "asset_status": "active",
                        },
                        {
                            "id": "candidate_style",
                            "type": "style",
                            "name": "Painterly Anime Garden",
                            "summary": "bright anime key art with painterly foliage",
                            "tags": ["anime", "garden"],
                            "asset_status": "active",
                        },
                        {
                            "id": "candidate_palette",
                            "type": "color_palette",
                            "name": "Amber Lotus Green",
                            "summary": "amber water and lotus green palette",
                            "tags": ["amber", "lotus"],
                            "asset_status": "active",
                        },
                    ]
                }
            )

            self.assertTrue(batch["visual_system_candidates"])
            system_candidate = batch["visual_system_candidates"][0]
            payload = system_candidate["payload"]
            self.assertEqual(payload["kind"], "worldview")
            self.assertEqual(payload["metadata"]["recommendation"], "suggest_create")
            self.assertEqual(payload["related_existing_assets"][0]["asset_id"], existing["id"])

            for candidate in batch["candidate_assets"]:
                store.decide_visual_asset_candidate(candidate["id"], "new_asset")
            confirmed = store.confirm_visual_system_candidate(system_candidate["id"])
            self.assertEqual(confirmed["status"], "confirmed")
            visual_system = confirmed["visual_system"]
            self.assertEqual(visual_system["kind"], "worldview")
            relation_asset_ids = {relation["asset_id"] for relation in visual_system["assets"]}
            self.assertIn(existing["id"], relation_asset_ids)
            self.assertEqual(len(relation_asset_ids), 4)

    def test_confirm_candidate_batch_creates_assets_system_and_recipe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "id": "candidate_scene",
                            "type": "scene",
                            "name": "Lotus Pond Garden",
                            "summary": "bright lotus pond with koi and stone platforms",
                            "asset_status": "active",
                        },
                        {
                            "id": "candidate_style",
                            "type": "style",
                            "name": "Painterly Anime Garden",
                            "summary": "bright anime key art with painterly foliage",
                            "asset_status": "active",
                        },
                        {
                            "id": "candidate_palette",
                            "type": "color_palette",
                            "name": "Amber Lotus Green",
                            "summary": "amber water and lotus green palette",
                            "asset_status": "active",
                        },
                    ],
                    "recipe_candidates": [
                        {
                            "name": "Lotus Wide Key Art",
                            "required_asset_types": ["scene", "style", "color_palette"],
                            "recommended_aspect_ratios": ["16:9"],
                            "recipe_assets": [
                                {"candidate_asset_id": "candidate_scene", "role": "core", "weight": 0.9},
                                {"candidate_asset_id": "candidate_style", "role": "core", "weight": 0.9},
                                {"candidate_asset_id": "candidate_palette", "role": "core", "weight": 0.8},
                            ],
                            "confidence": 0.65,
                        }
                    ],
                }
            )

            confirmed = store.confirm_visual_asset_candidate_batch(batch["batch_id"])
            self.assertEqual(len(confirmed["candidate_assets"]), 3)
            self.assertEqual(len(confirmed["visual_system_candidates"]), 1)
            self.assertEqual(len(confirmed["recipe_candidates"]), 1)

            system_id = confirmed["visual_system_candidates"][0]["confirmed_system_id"]
            recipe = confirmed["recipe_candidates"][0]["recipe"]
            self.assertIn(system_id, recipe["parent_system_ids"])
            self.assertEqual(len(recipe["assets"]), 3)
            self.assertEqual(store.get_visual_system(system_id)["kind"], "worldview")

    def test_generation_reuse_suggestions_create_recipe_and_system_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
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

            run = store.create_generation_run(
                {
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
                    "visual_review": {"style_consistency": "pass", "score": 0.92},
                    "outputs": [{"image_path": "/tmp/lotus.png"}],
                }
            )

            suggestions = run["reuse_suggestions"]
            self.assertEqual(len(suggestions["recipe_candidates"]), 1)
            self.assertEqual(len(suggestions["visual_system_candidates"]), 1)
            recipe_candidate = suggestions["recipe_candidates"][0]
            system_candidate = suggestions["visual_system_candidates"][0]
            self.assertEqual(recipe_candidate["payload"]["source"], "generation_run")
            self.assertEqual(system_candidate["payload"]["kind"], "worldview")

            repeated = store.suggest_generation_reuse(run["id"])
            self.assertEqual(len(repeated["recipe_candidates"]), 1)
            self.assertEqual(len(repeated["visual_system_candidates"]), 1)

            confirmed_system = store.confirm_visual_system_candidate(system_candidate["id"])
            confirmed_recipe = store.confirm_recipe_candidate(
                recipe_candidate["id"],
                parent_system_ids=[confirmed_system["confirmed_system_id"]],
            )
            self.assertIn(confirmed_system["confirmed_system_id"], confirmed_recipe["recipe"]["parent_system_ids"])

    def test_art_direction_suggestion_uses_fixed_visual_rule_categories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            batch = store.create_visual_asset_candidate_batch(
                {
                    "candidate_assets": [
                        {
                            "type": "color_palette",
                            "name": "Pastel Sky",
                            "summary": "clear pastel sky bands",
                        },
                        {
                            "type": "lighting",
                            "name": "Transparent Backlight",
                            "summary": "bright transparent backlight",
                        },
                        {
                            "type": "composition",
                            "name": "Open Aerial Depth",
                            "summary": "wide open aerial depth",
                        },
                    ]
                }
            )

            system_candidate = batch["visual_system_candidates"][0]
            payload = system_candidate["payload"]
            self.assertEqual(payload["kind"], "art_direction")
            self.assertEqual(
                [rule["key"] for rule in payload["visual_rules"]],
                [
                    "medium",
                    "rendering",
                    "color_lighting",
                    "composition_language",
                    "material_brush_edge",
                    "subject_aesthetic",
                ],
            )
            self.assertIn("clear pastel sky bands", payload["visual_rules"][2]["value"])
            self.assertIn("wide open aerial depth", payload["visual_rules"][3]["value"])

    def test_visual_system_candidate_attaches_to_recalled_existing_system(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Oriental Fantasy Painterly Style",
                    "summary": "bright painterly anime natural sanctuary",
                    "status": "active",
                }
            )
            system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Oriental Fantasy Natural Sanctuary",
                    "summary": "bright painterly anime natural sanctuary with spirit encounters",
                    "visual_rules": [
                        {"key": "medium", "value": ["painterly anime"]},
                        {"key": "subject_aesthetic", "value": ["natural sanctuary spirit encounter"]},
                    ],
                    "assets": [{"asset_id": style["id"], "role": "core", "weight": 0.9}],
                    "status": "active",
                }
            )
            candidate_asset = store.create_visual_asset_candidate(
                {
                    "type": "scene",
                    "name": "Golden Leaf Spirit Sanctuary",
                    "summary": "oriental fantasy natural sanctuary scene",
                    "status": "pending",
                }
            )
            candidate = store.create_visual_system_candidate(
                {
                    "batch_id": candidate_asset["batch_id"],
                    "kind": "art_direction",
                    "name": "Golden Leaf Spirit Art Direction",
                    "summary": "bright painterly anime natural sanctuary with leaf spirits",
                    "visual_rules": [
                        {"key": "medium", "value": ["painterly anime"]},
                        {"key": "subject_aesthetic", "value": ["leaf spirit natural sanctuary"]},
                    ],
                    "candidate_asset_relations": [
                        {"candidate_asset_id": candidate_asset["id"], "role": "core", "weight": 0.8}
                    ],
                    "existing_asset_relations": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.8}
                    ],
                    "status": "pending",
                }
            )

            self.assertEqual(candidate["payload"]["metadata"]["recommendation"], "attach_evidence")
            self.assertEqual(candidate["payload"]["metadata"]["evolution_action"], "attach_evidence")
            confirmed_asset = store.decide_visual_asset_candidate(candidate_asset["id"], "new_asset")
            confirmed = store.confirm_visual_system_candidate(candidate["id"])
            self.assertEqual(confirmed["confirmed_system_id"], system["id"])
            relation_asset_ids = {
                relation["asset_id"]
                for relation in store.list_visual_system_assets(system_id=system["id"])
            }
            self.assertIn(confirmed_asset["confirmed_asset_id"], relation_asset_ids)

    def test_recipe_candidate_merges_into_recalled_existing_recipe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset({"type": "style", "name": "Painterly Fantasy", "status": "active"})
            scene = store.create_visual_asset({"type": "scene", "name": "Spirit Grove", "status": "active"})
            system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Fantasy Grove",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["spirit grove"]}],
                    "assets": [{"asset_id": style["id"], "role": "core"}],
                    "status": "active",
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Fantasy Grove Key Art",
                    "summary": "painterly spirit grove key art",
                    "parent_system_ids": [system["id"]],
                    "composition_rules": [{"key": "asset_roles", "value": ["style and scene define key art"]}],
                    "assets": [{"asset_id": style["id"], "role": "core"}],
                    "status": "active",
                }
            )
            candidate = store.create_recipe_candidate(
                {
                    "name": "Fantasy Grove Key Art Variant",
                    "summary": "painterly spirit grove key art",
                    "parent_system_ids": [system["id"]],
                    "composition_rules": [{"key": "asset_roles", "value": ["style and scene define key art"]}],
                    "recipe_assets": [
                        {"asset_id": style["id"], "role": "core"},
                        {"asset_id": scene["id"], "role": "optional"},
                    ],
                    "status": "pending",
                }
            )

            self.assertEqual(candidate["payload"]["metadata"]["recommendation"], "attach_evidence")
            self.assertEqual(candidate["payload"]["metadata"]["evolution_action"], "attach_evidence")
            confirmed = store.confirm_recipe_candidate(candidate["id"])
            self.assertEqual(confirmed["confirmed_recipe_id"], recipe["id"])
            relation_asset_ids = {
                relation["asset_id"]
                for relation in store.list_recipe_assets(recipe_id=recipe["id"])
            }
            self.assertIn(scene["id"], relation_asset_ids)

    def test_embedding_status_and_disabled_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()
            store.create_visual_asset({"type": "style", "name": "Soft Paint", "status": "active"})

            status = store.embedding_status({"embedding": {"provider": "disabled"}})
            self.assertEqual(status["provider"], "disabled")
            self.assertFalse(status["needs_rebuild"])
            result = store.index_embeddings({"embedding": {"provider": "disabled"}}, entity_type="visual_asset")
            self.assertEqual(result["skipped"][0]["reason"], "embedding provider disabled")

    def test_candidate_dedupe_uses_configured_semantic_embedding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            embed_script = root / "fake_embed.py"
            embed_script.write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "body = json.load(sys.stdin)",
                        "vectors = []",
                        "for text in body.get('texts', []):",
                        "    lowered = text.lower()",
                        "    if any(term in lowered for term in ['celestial', 'lunar', 'moon']):",
                        "        vectors.append([1.0, 0.0])",
                        "    else:",
                        "        vectors.append([0.0, 1.0])",
                        "json.dump({'vectors': vectors}, sys.stdout)",
                    ]
                ),
                encoding="utf-8",
            )
            config = {
                "embedding": {
                    "provider": "local",
                    "model": "fake-semantic",
                    "providers": {
                        "local": {
                            "command": f"{sys.executable} {embed_script}",
                            "model": "fake-semantic",
                            "dimensions": 2,
                        }
                    },
                }
            }
            store = AetherStore(root / "aether.sqlite")
            store.init()
            asset = store.create_visual_asset(
                {
                    "type": "scene",
                    "name": "Celestial Waterfall Gate",
                    "summary": "celestial waterfall glowing arch",
                    "status": "active",
                }
            )
            system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Celestial Vista Direction",
                    "summary": "celestial luminous gateway scene direction",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["celestial gateway"]}],
                    "assets": [{"asset_id": asset["id"], "role": "core"}],
                    "status": "active",
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Celestial Gateway Key Art",
                    "summary": "celestial luminous gateway composition",
                    "parent_system_ids": [system["id"]],
                    "composition_rules": [{"key": "subject_scene_binding", "value": ["gateway dominates the scene"]}],
                    "assets": [{"asset_id": asset["id"], "role": "core"}],
                    "status": "active",
                }
            )
            store.index_embeddings(config)
            status = store.embedding_status(config)
            self.assertEqual(status["index_health"]["visual_asset"]["current"], 1)
            self.assertEqual(status["index_health"]["visual_system"]["current"], 1)
            self.assertEqual(status["index_health"]["recipe"]["current"], 1)
            self.assertFalse(status["needs_rebuild"])

            candidate = store.create_visual_asset_candidate(
                {
                    "type": "scene",
                    "name": "Lunar Cascade Entrance",
                    "summary": "moonlit cascade threshold",
                    "status": "pending",
                },
                config=config,
            )

            self.assertEqual(candidate["similar_candidates"][0]["asset_id"], asset["id"])
            self.assertEqual(candidate["similar_candidates"][0]["semantic_score"], 1.0)
            self.assertEqual(candidate["decision"], "existing_asset")

            system_candidate = store.create_visual_system_candidate(
                {
                    "kind": "art_direction",
                    "name": "Lunar Gate Direction",
                    "summary": "moonlit threshold scene direction",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["lunar gate"]}],
                    "related_existing_systems": [{"system_id": "stale_system", "similarity_score": 0.99}],
                    "metadata": {
                        "recommendation": "suggest_create",
                        "target_system_id": "stale_system",
                        "dedupe_score": 0.99,
                    },
                    "status": "pending",
                },
                config=config,
            )
            self.assertEqual(system_candidate["payload"]["metadata"]["recommendation"], "attach_evidence")
            self.assertEqual(system_candidate["payload"]["metadata"]["evolution_action"], "attach_evidence")
            self.assertEqual(system_candidate["payload"]["metadata"]["target_system_id"], system["id"])
            self.assertNotEqual(system_candidate["payload"]["related_existing_systems"][0]["system_id"], "stale_system")
            self.assertEqual(system_candidate["payload"]["related_existing_systems"][0]["semantic_score"], 1.0)

            recipe_candidate = store.create_recipe_candidate(
                {
                    "name": "Moon Gate Composition",
                    "summary": "lunar threshold composition",
                    "composition_rules": [{"key": "subject_scene_binding", "value": ["moon gate dominates the scene"]}],
                    "related_existing_recipes": [{"recipe_id": "stale_recipe", "semantic_score": 0.99}],
                    "metadata": {
                        "recommendation": "suggest_create",
                        "target_recipe_id": "stale_recipe",
                        "dedupe_score": 0.99,
                    },
                    "status": "pending",
                },
                config=config,
            )
            self.assertEqual(recipe_candidate["payload"]["metadata"]["recommendation"], "attach_evidence")
            self.assertEqual(recipe_candidate["payload"]["metadata"]["evolution_action"], "attach_evidence")
            self.assertEqual(recipe_candidate["payload"]["metadata"]["target_recipe_id"], recipe["id"])
            self.assertNotEqual(recipe_candidate["payload"]["related_existing_recipes"][0]["recipe_id"], "stale_recipe")
            self.assertEqual(recipe_candidate["payload"]["related_existing_recipes"][0]["semantic_score"], 1.0)

    def test_asset_candidate_recall_decision_is_storage_owned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            existing = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Painterly Anime Garden",
                    "summary": "bright anime key art with painterly foliage",
                    "tags": ["anime", "garden"],
                    "status": "active",
                }
            )
            candidate = store.create_visual_asset_candidate(
                {
                    "id": "candidate_style",
                    "batch_id": "batch_storage_owned",
                    "type": "style",
                    "name": "Painterly Anime Festival Variant",
                    "summary": "bright anime key art with painterly foliage and festival lanterns",
                    "tags": ["anime", "garden", "festival"],
                    "decision": "new_asset",
                    "reuse_score": 0,
                    "target_asset_id": "stale_asset",
                    "status": "pending",
                }
            )

            self.assertEqual(candidate["payload"]["evolution_action"], "inherit_variant")
            self.assertEqual(candidate["payload"]["evolution_suggestion"]["action"], "inherit_variant")
            self.assertEqual(candidate["decision"], "asset_variant")
            self.assertEqual(candidate["target_asset_id"], existing["id"])
            self.assertEqual(candidate["payload"]["target_asset_id"], existing["id"])
            self.assertGreater(candidate["reuse_score"], 0)

            with store.connect() as conn:
                conn.execute(
                    "update visual_asset_candidates set decision = 'new_asset', target_asset_id = null where id = ?",
                    (candidate["id"],),
                )

            confirmed = store.confirm_visual_asset_candidate_batch("batch_storage_owned")
            confirmed_candidate = confirmed["candidate_assets"][0]
            variant_asset = store.get_visual_asset(confirmed_candidate["confirmed_asset_id"])
            self.assertEqual(confirmed_candidate["decision"], "asset_variant")
            self.assertEqual(confirmed_candidate["target_asset_id"], existing["id"])
            self.assertEqual(variant_asset["parent_asset_id"], existing["id"])

    def test_evolvable_actions_record_evidence_revisions_and_lineage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset({"type": "style", "name": "Painterly Anime", "status": "active"})
            variant_candidate = store.create_visual_asset_candidate(
                {
                    "type": "style",
                    "name": "Painterly Anime Festival Variant",
                    "summary": "painterly anime with festival accents",
                    "status": "pending",
                }
            )
            variant = store.decide_visual_asset_candidate(
                variant_candidate["id"],
                "inherit_variant",
                target_asset_id=style["id"],
            )
            variant_asset = store.get_visual_asset(variant["confirmed_asset_id"])
            self.assertEqual(variant_asset["parent_asset_id"], style["id"])
            self.assertEqual(store.list_revisions("visual_asset", variant_asset["id"])[0]["action"], "inherit_variant")

            system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Painterly Direction",
                    "summary": "painterly anime art direction",
                    "visual_rules": [{"key": "medium", "value": ["painterly anime"]}],
                    "status": "active",
                }
            )
            candidate = store.create_visual_system_candidate(
                {
                    "kind": "art_direction",
                    "name": "Painterly Direction Evidence",
                    "summary": "painterly anime art direction",
                    "visual_rules": [{"key": "medium", "value": ["painterly anime"]}],
                    "status": "pending",
                }
            )
            confirmed = store.confirm_visual_system_candidate(
                candidate["id"],
                target_system_id=system["id"],
                action="attach_evidence",
            )
            self.assertEqual(confirmed["confirmed_system_id"], system["id"])
            self.assertEqual(store.list_visual_system_evidence(system["id"])[0]["source_candidate_id"], candidate["id"])
            self.assertEqual(store.list_revisions("visual_system", system["id"])[0]["action"], "attach_evidence")

            child_candidate = store.create_visual_system_candidate(
                {
                    "kind": "art_direction",
                    "name": "Festival Painterly Direction",
                    "summary": "painterly anime festival branch",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["festival branch"]}],
                    "status": "pending",
                }
            )
            child_confirmed = store.confirm_visual_system_candidate(
                child_candidate["id"],
                target_system_id=system["id"],
                action="inherit_variant",
            )
            child = store.get_visual_system(child_confirmed["confirmed_system_id"])
            self.assertEqual(child["parent_system_id"], system["id"])

            recipe = store.create_recipe(
                {
                    "name": "Painterly Key Art",
                    "summary": "painterly key art",
                    "composition_rules": [{"key": "asset_roles", "value": ["style defines rendering"]}],
                    "status": "active",
                }
            )
            recipe_candidate = store.create_recipe_candidate(
                {
                    "name": "Festival Painterly Key Art",
                    "summary": "painterly festival key art",
                    "composition_rules": [{"key": "asset_roles", "value": ["style defines rendering"]}],
                    "status": "pending",
                }
            )
            recipe_confirmed = store.confirm_recipe_candidate(
                recipe_candidate["id"],
                target_recipe_id=recipe["id"],
                action="inherit_variant",
            )
            child_recipe = store.get_recipe(recipe_confirmed["confirmed_recipe_id"])
            self.assertEqual(child_recipe["parent_recipe_id"], recipe["id"])

    def test_merge_preview_abstracts_and_marks_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            target = store.create_visual_asset(
                {
                    "type": "mood",
                    "name": "Warm Festival Mood",
                    "summary": "warm abundant festival atmosphere",
                    "tags": ["warm", "festival"],
                    "profile": {"emotional_tone": "joyful"},
                    "prompt_fragments": ["warm festival abundance"],
                    "status": "active",
                }
            )
            source = store.create_visual_asset(
                {
                    "type": "mood",
                    "name": "Abundant Lantern Mood",
                    "summary": "warm lantern celebration atmosphere",
                    "tags": ["warm", "lantern"],
                    "profile": {"atmosphere": "celebration"},
                    "prompt_fragments": ["warm festival abundance", "lantern celebration"],
                    "status": "active",
                }
            )
            preview = store.visual_asset_merge_preview(source["id"], target["id"])
            self.assertEqual(preview["action"], "merge_existing")
            self.assertLessEqual(len(preview["proposed_after"]["prompt_fragments"]), 8)
            merged = store.merge_visual_asset(source["id"], target["id"])
            self.assertEqual(merged["status"], "merged")
            self.assertEqual(merged["merged_into_asset_id"], target["id"])
            self.assertEqual(store.list_revisions("visual_asset", target["id"])[0]["action"], "merge_existing")

            system_a = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Festival Direction A",
                    "visual_rules": [{"key": "medium", "value": ["painterly anime"]}],
                    "status": "active",
                }
            )
            system_b = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Festival Direction B",
                    "visual_rules": [{"key": "medium", "value": ["painterly anime"]}],
                    "status": "active",
                }
            )
            system_merge = store.merge_visual_system(system_b["id"], system_a["id"])
            self.assertEqual(system_merge["merged"]["merged_into_system_id"], system_a["id"])

            recipe_a = store.create_recipe(
                {
                    "name": "Festival Recipe A",
                    "composition_rules": [{"key": "asset_roles", "value": ["style defines rendering"]}],
                    "status": "active",
                }
            )
            recipe_b = store.create_recipe(
                {
                    "name": "Festival Recipe B",
                    "composition_rules": [{"key": "asset_roles", "value": ["style defines rendering"]}],
                    "status": "active",
                }
            )
            recipe_merge = store.merge_recipe(recipe_b["id"], recipe_a["id"])
            self.assertEqual(recipe_merge["merged"]["merged_into_recipe_id"], recipe_a["id"])

    def test_recall_excludes_merged_deprecated_and_archived_entities_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            active_asset = store.create_visual_asset(
                {"type": "style", "name": "Recallable Festival Style", "summary": "festival recall anchor", "status": "active"}
            )
            store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Merged Festival Style",
                    "summary": "festival recall anchor",
                    "status": "active",
                    "merged_into_asset_id": active_asset["id"],
                }
            )
            store.create_visual_asset(
                {"type": "style", "name": "Deprecated Festival Style", "summary": "festival recall anchor", "status": "deprecated"}
            )
            asset_ids = {item["asset_id"] for item in store.hybrid_recall("visual_asset", "festival recall anchor", limit=10)}
            self.assertEqual(asset_ids, {active_asset["id"]})

            active_system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Recallable Festival Direction",
                    "summary": "festival recall direction",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["festival"]}],
                    "status": "active",
                }
            )
            store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Merged Festival Direction",
                    "summary": "festival recall direction",
                    "visual_rules": [{"key": "subject_aesthetic", "value": ["festival"]}],
                    "status": "active",
                    "merged_into_system_id": active_system["id"],
                }
            )
            system_ids = {item["system_id"] for item in store.hybrid_recall("visual_system", "festival recall direction", limit=10)}
            self.assertEqual(system_ids, {active_system["id"]})

            active_recipe = store.create_recipe({"name": "Recallable Festival Recipe", "summary": "festival recall recipe", "status": "active"})
            store.create_recipe(
                {
                    "name": "Merged Festival Recipe",
                    "summary": "festival recall recipe",
                    "status": "active",
                    "merged_into_recipe_id": active_recipe["id"],
                }
            )
            store.create_recipe({"name": "Archived Festival Recipe", "summary": "festival recall recipe", "status": "archived"})
            recipe_ids = {item["recipe_id"] for item in store.hybrid_recall("recipe", "festival recall recipe", limit=10)}
            self.assertEqual(recipe_ids, {active_recipe["id"]})

    def test_liked_feedback_triggers_generation_reuse_suggestion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset({"type": "style", "name": "Soft Anime", "status": "active"})
            palette = store.create_visual_asset({"type": "color_palette", "name": "Quiet Blue", "status": "active"})
            run = store.create_generation_run(
                {
                    "source_prompt": "quiet portrait",
                    "refined_prompt": "quiet portrait",
                    "selected_assets": [
                        {"asset_id": style["id"], "type": "style"},
                        {"asset_id": palette["id"], "type": "color_palette"},
                    ],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "visual_review": {"style_consistency": "not_reviewed"},
                    "outputs": [],
                }
            )
            self.assertNotIn("reuse_suggestions", run)

            updated = store.update_generation_feedback(run["id"], {"liked": True}, "liked")
            self.assertIn("reuse_suggestions", updated)
            self.assertEqual(len(updated["reuse_suggestions"]["recipe_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
