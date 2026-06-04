import json
import tempfile
import unittest
from pathlib import Path

from aether_core.config import load_config
from aether_core.panel import PANEL_HTML, collect_panel_data
from aether_core.panel_bundle import export_panel_bundle, import_panel_bundle
from aether_core.storage import AetherStore


def write_config(root: Path) -> Path:
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
    return config_path


class PanelTests(unittest.TestCase):
    def test_panel_defaults_to_active_favorites(self):
        self.assertIn('data-view="favorites">Favorites</button>', PANEL_HTML)
        self.assertIn('data-view="recipes">Recipes</button>', PANEL_HTML)
        self.assertIn('view: "favorites"', PANEL_HTML)
        self.assertIn('status: "active"', PANEL_HTML)
        self.assertIn('detail: null', PANEL_HTML)
        self.assertIn('status.value = state.status;', PANEL_HTML)
        self.assertIn('class="detail-media"', PANEL_HTML)
        self.assertIn('function existingImages(images)', PANEL_HTML)
        self.assertIn('image.exists !== false', PANEL_HTML)
        self.assertIn('function ruleItem(item)', PANEL_HTML)
        self.assertIn('item.key || item.name || item.type || "Rule"', PANEL_HTML)
        self.assertIn('href="/api/export"', PANEL_HTML)
        self.assertIn('fetch(`/api/import?mode=${encodeURIComponent(mode)}`', PANEL_HTML)
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

    def test_panel_data_deduplicates_images_by_content_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = load_config(write_config(root))
            store = AetherStore(config.database_path)
            store.init()
            generated_path = root / "generated.png"
            generated_path.write_bytes(b"same generated image")
            first = store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(generated_path),
                    "asset_path": str(generated_path),
                    "sha256": "same-sha",
                    "mime_type": "image/png",
                    "size_bytes": generated_path.stat().st_size,
                }
            )
            duplicate = store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(generated_path),
                    "asset_path": str(generated_path),
                    "sha256": "same-sha",
                    "mime_type": "image/png",
                    "size_bytes": generated_path.stat().st_size,
                }
            )
            visual_asset = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Duplicate Generated Style",
                    "summary": "A style with duplicated generated outputs.",
                }
            )
            store.create_generation_run(
                {
                    "source_prompt": "source",
                    "refined_prompt": "refined",
                    "generation_skill": "test",
                    "selected_assets": [{"asset_id": visual_asset["id"]}],
                    "outputs": [
                        {"asset_id": first["id"], "asset_path": first["asset_path"]},
                        {"asset_id": duplicate["id"], "asset_path": duplicate["asset_path"]},
                    ],
                    "status": "generated",
                }
            )

            data = collect_panel_data(config, store)
            panel_asset = next(item for item in data["visual_assets"] if item["id"] == visual_asset["id"])

            self.assertEqual([image["id"] for image in panel_asset["generated_images"]], [first["id"]])

    def test_panel_bundle_exports_and_imports_material_library(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            source_config = load_config(write_config(source_root))
            source_store = AetherStore(source_config.database_path)
            source_store.init()

            reference_path = source_root / "reference.png"
            generated_path = source_root / "generated.png"
            reference_path.write_bytes(b"reference")
            generated_path.write_bytes(b"generated")
            reference = source_store.create_asset(
                {
                    "kind": "reference",
                    "source_path": str(reference_path),
                    "asset_path": str(reference_path),
                    "sha256": "reference",
                    "mime_type": "image/png",
                    "size_bytes": reference_path.stat().st_size,
                }
            )
            generated = source_store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(generated_path),
                    "asset_path": str(generated_path),
                    "sha256": "generated",
                    "mime_type": "image/png",
                    "size_bytes": generated_path.stat().st_size,
                }
            )
            visual_asset = source_store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Bundle Style",
                    "summary": "Exported style.",
                    "status": "active",
                    "source_references": [{"asset_id": reference["id"], "image_path": reference["asset_path"]}],
                }
            )
            system = source_store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Bundle System",
                    "summary": "Exported system.",
                    "status": "active",
                    "source_reference_ids": [reference["id"]],
                }
            )
            source_store.set_visual_system_asset(system["id"], {"asset_id": visual_asset["id"], "role": "core"})
            recipe = source_store.create_recipe(
                {
                    "name": "Bundle Recipe",
                    "summary": "Exported recipe.",
                    "status": "active",
                    "parent_system_ids": [system["id"]],
                    "source_reference_ids": [reference["id"]],
                }
            )
            source_store.set_recipe_asset(recipe["id"], {"asset_id": visual_asset["id"], "role": "core"})
            generation = source_store.create_generation_run(
                {
                    "source_prompt": "source",
                    "refined_prompt": "refined",
                    "generation_skill": "test",
                    "selected_assets": [{"asset_id": visual_asset["id"], "name": visual_asset["name"]}],
                    "outputs": [{"asset_id": generated["id"], "asset_path": generated["asset_path"]}],
                    "status": "generated",
                }
            )
            source_store.set_panel_favorite("recipe", recipe["id"], True)

            bundle, filename = export_panel_bundle(source_config, source_store)
            self.assertTrue(filename.endswith(".zip"))
            self.assertTrue(bundle.startswith(b"PK"))

            target_root = Path(target_dir)
            target_config = load_config(write_config(target_root))
            target_store = AetherStore(target_config.database_path)
            target_store.init()
            result = import_panel_bundle(target_config, target_store, bundle, mode="replace")

            self.assertEqual(result["counts"]["assets"], 2)
            self.assertEqual(result["counts"]["visual_assets"], 1)
            self.assertEqual(result["counts"]["visual_systems"], 1)
            self.assertEqual(result["counts"]["recipes"], 1)
            self.assertEqual(result["counts"]["generation_runs"], 1)
            imported_reference = target_store.list_assets(kind="reference", limit=None)[0]
            imported_generated = target_store.list_assets(kind="generated", limit=None)[0]
            self.assertTrue(Path(imported_reference["asset_path"]).exists())
            self.assertTrue(Path(imported_generated["asset_path"]).exists())
            self.assertIn(str(target_root), imported_reference["asset_path"])
            self.assertIn(str(target_root), imported_generated["asset_path"])

            imported_asset = target_store.get_visual_asset(visual_asset["id"])
            imported_generation = target_store.get_generation_run(generation["id"])
            self.assertIsNotNone(imported_asset)
            self.assertIsNotNone(imported_generation)
            assert imported_asset is not None
            assert imported_generation is not None
            self.assertIn(str(target_root), imported_asset["source_references"][0]["image_path"])
            self.assertIn(str(target_root), imported_generation["outputs"][0]["asset_path"])
            self.assertEqual(target_store.list_visual_system_assets(system_id=system["id"])[0]["asset_id"], visual_asset["id"])
            self.assertEqual(target_store.list_recipe_assets(recipe_id=recipe["id"])[0]["asset_id"], visual_asset["id"])

            panel_data = collect_panel_data(target_config, target_store)
            self.assertEqual(panel_data["summary"]["favorite_count"], 1)
            self.assertEqual(panel_data["favorites"][0]["id"], recipe["id"])


if __name__ == "__main__":
    unittest.main()
