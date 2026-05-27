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


if __name__ == "__main__":
    unittest.main()
