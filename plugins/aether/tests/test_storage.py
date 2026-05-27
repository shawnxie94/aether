import tempfile
import unittest
from pathlib import Path

from aether_core.storage import AetherStore


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
                        "art_style": "cinematic cyberpunk",
                        "lighting": "neon rim light",
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
                    "visual_rules": ["preserve tactile paper"],
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
            self.assertEqual(len(store.get_recipe(recipe["id"])["assets"]), 2)

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
