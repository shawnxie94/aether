import tempfile
import unittest
from pathlib import Path

from aether_core.composer import compose_prompt
from aether_core.storage import AetherStore


class ComposerTests(unittest.TestCase):
    def test_compose_prompt_selects_assets_and_detects_conflicts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Digital Melancholy",
                    "summary": "muted lonely cinematic future style",
                    "tags": ["lonely", "future"],
                    "prompt_fragments": ["digital melancholy", "muted cinematic realism"],
                    "negative_fragments": ["cheerful cartoon"],
                    "recommended_aspect_ratios": ["16:9"],
                    "status": "active",
                }
            )
            lighting = store.create_visual_asset(
                {
                    "type": "lighting",
                    "name": "Rainy Neon Reflection",
                    "summary": "neon rain reflections",
                    "tags": ["rain", "neon"],
                    "prompt_fragments": ["rain-soaked neon reflections"],
                    "negative_fragments": ["flat lighting"],
                    "status": "active",
                }
            )
            store.create_visual_asset(
                {
                    "type": "composition",
                    "name": "Minimal Negative Space",
                    "summary": "minimal negative space",
                    "tags": ["minimal"],
                    "prompt_fragments": ["large negative space"],
                    "avoid_with": [lighting["id"]],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "lonely girl in a future rainy city",
                explicit_asset_ids=[style["id"]],
                query="neon rain",
                default_generation_params={"quality": "standard"},
            )

            selected_ids = {item["asset_id"] for item in record["selected_assets"]}
            self.assertIn(style["id"], selected_ids)
            self.assertIn(lighting["id"], selected_ids)
            self.assertEqual(record["generation_params"]["aspectRatio"], "16:9")
            self.assertIn("digital melancholy", record["refined_prompt"])
            self.assertIn("flat lighting", record["negative_prompt"])
            self.assertTrue(record["conflicts"])


if __name__ == "__main__":
    unittest.main()
