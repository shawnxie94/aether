import tempfile
import unittest
from pathlib import Path

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
                }
            )
            self.assertTrue(prompt["id"].startswith("prompt_"))

            generation = store.create_generation_run(
                {
                    "source_prompt": "lonely girl in future city",
                    "refined_prompt": prompt["refined_prompt"],
                    "style_id": style["id"],
                    "generation_skill": "imagegen",
                    "status": "generated",
                    "outputs": ["generated.png"],
                }
            )
            updated = store.update_generation_feedback(
                generation["id"], {"liked": True, "notes": "works"}, "liked"
            )

            self.assertEqual(updated["status"], "liked")
            self.assertTrue(updated["feedback"]["liked"])

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


if __name__ == "__main__":
    unittest.main()
