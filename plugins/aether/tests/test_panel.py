import json
import tempfile
import unittest
from pathlib import Path

from aether_core.config import load_config
from aether_core.panel import PANEL_HTML, collect_panel_data
from aether_core.storage import AetherStore


class PanelTests(unittest.TestCase):
    def test_panel_defaults_to_active_recipes(self):
        self.assertIn('data-view="recipes">Recipes</button>', PANEL_HTML)
        self.assertIn('view: "recipes"', PANEL_HTML)
        self.assertIn('status: "active"', PANEL_HTML)
        self.assertIn('detail: null', PANEL_HTML)
        self.assertIn('status.value = state.status;', PANEL_HTML)
        self.assertIn('class="detail-media"', PANEL_HTML)
        self.assertIn('function existingImages(images)', PANEL_HTML)
        self.assertIn('image.exists !== false', PANEL_HTML)
        self.assertIn('function ruleItem(item)', PANEL_HTML)
        self.assertIn('item.key || item.name || item.type || "Rule"', PANEL_HTML)
        self.assertNotIn('data-view="files"', PANEL_HTML)

    def test_panel_data_links_reference_and_generated_images_to_visual_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
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
                        "backend": {"host": "127.0.0.1", "port": 3850},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            store = AetherStore(config.database_path)
            store.init()
            reference_path = root / "reference.png"
            generated_path = root / "generated.png"
            reference_path.write_bytes(b"reference")
            generated_path.write_bytes(b"generated")

            reference = store.create_asset(
                {
                    "kind": "reference",
                    "source_path": str(reference_path),
                    "asset_path": str(reference_path),
                    "sha256": "reference",
                    "mime_type": "image/png",
                    "size_bytes": reference_path.stat().st_size,
                }
            )
            generated = store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(generated_path),
                    "asset_path": str(generated_path),
                    "sha256": "generated",
                    "mime_type": "image/png",
                    "size_bytes": generated_path.stat().st_size,
                }
            )
            visual_asset = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Panel Style",
                    "summary": "A style shown in the local panel.",
                    "source_references": [
                        {
                            "asset_id": reference["id"],
                            "image_path": reference["asset_path"],
                        }
                    ],
                }
            )
            store.create_generation_run(
                {
                    "source_prompt": "source",
                    "refined_prompt": "refined",
                    "generation_skill": "test",
                    "selected_assets": [{"asset_id": visual_asset["id"], "name": visual_asset["name"]}],
                    "outputs": [
                        {
                            "asset_id": generated["id"],
                            "asset_path": generated["asset_path"],
                            "image_path": generated["asset_path"],
                        }
                    ],
                    "status": "generated",
                }
            )
            recipe = store.create_recipe({"name": "Favorite Recipe", "summary": "A saved recipe.", "status": "active"})
            store.set_panel_favorite("recipe", recipe["id"], True)

            data = collect_panel_data(config, store)
            panel_asset = next(item for item in data["visual_assets"] if item["id"] == visual_asset["id"])
            panel_recipe = next(item for item in data["recipes"] if item["id"] == recipe["id"])

            self.assertEqual(data["summary"]["visual_asset_count"], 1)
            self.assertEqual(data["summary"]["reference_file_count"], 1)
            self.assertEqual(data["summary"]["generated_file_count"], 1)
            self.assertEqual(data["summary"]["favorite_count"], 1)
            self.assertTrue(panel_recipe["is_favorite"])
            self.assertEqual(data["favorites"][0]["id"], recipe["id"])
            self.assertEqual(panel_asset["reference_images"][0]["id"], reference["id"])
            self.assertEqual(panel_asset["generated_images"][0]["id"], generated["id"])


if __name__ == "__main__":
    unittest.main()
