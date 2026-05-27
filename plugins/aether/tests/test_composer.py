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

    def test_compose_prompt_uses_visual_systems_and_recipes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Oil Pastel Anime",
                    "summary": "hand drawn oil pastel anime",
                    "prompt_fragments": ["hand drawn oil pastel anime"],
                    "recommended_aspect_ratios": ["4:3"],
                    "status": "active",
                }
            )
            texture = store.create_visual_asset(
                {
                    "type": "texture",
                    "name": "Paper Grain",
                    "summary": "toothy off white paper grain",
                    "prompt_fragments": ["toothy off-white paper texture"],
                    "status": "active",
                }
            )
            palette = store.create_visual_asset(
                {
                    "type": "color_palette",
                    "name": "Muted Night",
                    "summary": "quiet muted night blues",
                    "prompt_fragments": ["muted night blue palette"],
                    "status": "active",
                }
            )
            system = store.create_visual_system(
                {
                    "kind": "genre",
                    "name": "Oil Pastel Daily Anime",
                    "visual_rules": ["preserve tactile handmade paper feel"],
                    "avoid_rules": ["avoid glossy 3D rendering"],
                    "assets": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.9},
                        {"asset_id": palette["id"], "role": "optional", "weight": 0.7},
                    ],
                    "status": "active",
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Oil Pastel Portrait",
                    "parent_system_ids": [system["id"]],
                    "recommended_aspect_ratios": ["3:4"],
                    "assets": [
                        {"asset_id": texture["id"], "role": "core", "weight": 0.9},
                    ],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "quiet girl portrait",
                system_ids=[system["id"]],
                recipe_ids=[recipe["id"]],
                default_generation_params={"aspectRatio": "1:1", "quality": "standard"},
            )

            selected_ids = {item["asset_id"] for item in record["selected_assets"]}
            self.assertIn(style["id"], selected_ids)
            self.assertIn(texture["id"], selected_ids)
            self.assertIn(palette["id"], selected_ids)
            self.assertEqual(record["generation_params"]["aspectRatio"], "3:4")
            self.assertIn("preserve tactile handmade paper feel", record["refined_prompt"])
            self.assertIn("avoid glossy 3D rendering", record["negative_prompt"])
            self.assertIn("preserve tactile handmade paper feel", record["composition_plan"]["system_rules"])
            self.assertEqual(record["constraints"]["selected_systems"][0]["system_id"], system["id"])
            self.assertEqual(record["constraints"]["selected_recipes"][0]["recipe_id"], recipe["id"])


if __name__ == "__main__":
    unittest.main()
