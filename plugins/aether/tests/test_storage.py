import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aether_core.cli import style_description, style_summary
from aether_core.storage import AetherStore


class StorageTests(unittest.TestCase):
    def test_style_prompt_generation_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_style(
                {
                    "name": "Neon Melancholy",
                    "summary": "lonely neon city style",
                    "tags": ["neon", "cinematic"],
                    "status": "active",
                    "style_profile": {
                        "art_style": "cinematic cyberpunk",
                        "lighting": "neon rim light",
                    },
                }
            )

            self.assertEqual(style["status"], "active")
            self.assertEqual(len(store.list_styles()), 1)
            self.assertEqual(store.get_style(style["id"])["name"], "Neon Melancholy")

            prompt = store.save_prompt_record(
                {
                    "source_prompt": "lonely girl in future city",
                    "style_id": style["id"],
                    "refined_prompt": "cinematic neon lonely girl in future city",
                    "negative_prompt": "flat lighting",
                    "generation_params": {"aspectRatio": "16:9"},
                }
            )
            self.assertTrue(prompt["id"].startswith("prompt_"))
            self.assertEqual(prompt["generation_params"]["aspectRatio"], "16:9")

            generation = store.create_generation_run(
                {
                    "source_prompt": "lonely girl in future city",
                    "refined_prompt": prompt["refined_prompt"],
                    "style_id": style["id"],
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

            archived = store.update_style_status(style["id"], "archived")
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

    def test_style_catalog_summary_and_description(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AetherStore(root / "aether.sqlite")
            store.init()

            style = store.create_style(
                {
                    "name": "Soft Editorial",
                    "summary": "quiet studio editorial look",
                    "tags": ["editorial"],
                    "source_references": [
                        {
                            "image_path": "references/soft-editorial.png",
                            "source_prompt": "soft studio portrait",
                            "role": "positive_reference",
                        }
                    ],
                    "style_profile": {"lighting": "large softbox", "mood": "calm"},
                    "prompt_template": "{source_prompt}, soft editorial lighting",
                    "negative_prompt": "harsh shadows",
                    "status": "active",
                }
            )

            summary = style_summary(style)
            self.assertEqual(summary["id"], style["id"])
            self.assertEqual(summary["reference_count"], 1)
            self.assertNotIn("style_profile", summary)

            config = SimpleNamespace(resolve_path=lambda value: (root / value).resolve())
            description = style_description(config, style)
            self.assertEqual(description["parameter_definition"]["style_profile"]["lighting"], "large softbox")
            self.assertEqual(description["parameter_definition"]["negative_prompt"], "harsh shadows")
            self.assertEqual(
                description["reference_images"][0]["display_path"],
                str((root / "references/soft-editorial.png").resolve()),
            )

    def test_generation_list_get_and_stats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            first = store.create_generation_run(
                {
                    "source_prompt": "source one",
                    "refined_prompt": "refined one",
                    "style_id": "style_a",
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
                    "style_id": "style_a",
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
            self.assertEqual(len(store.list_generation_runs(style_id="style_a")), 2)
            self.assertEqual(len(store.list_generation_runs(review="major_deviation")), 1)
            self.assertEqual(store.list_generation_runs(status="liked")[0]["id"], second["id"])

            stats = store.generation_stats(style_id="style_a")
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["by_review"]["major_deviation"], 1)
            self.assertEqual(stats["by_review"]["pass"], 1)
            self.assertEqual(stats["feedback"]["liked"], 1)
            self.assertEqual(stats["common_deviations"][0]["deviation"], "lost texture")


if __name__ == "__main__":
    unittest.main()
