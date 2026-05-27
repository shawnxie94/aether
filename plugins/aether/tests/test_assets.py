import json
import tempfile
import unittest
from pathlib import Path

from aether_core.assets import ingest_asset
from aether_core.config import load_config
from aether_core.storage import AetherStore


class AssetTests(unittest.TestCase):
    def test_ingest_asset_copies_and_hashes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            source.write_bytes(b"fake image")
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": "aether.sqlite",
                            "assetRoot": "assets",
                            "referenceImageDir": "assets/references",
                            "generatedImageDir": "assets/generated",
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)

            asset = ingest_asset(config, source, "reference")

            self.assertEqual(asset["kind"], "reference")
            self.assertTrue(Path(asset["asset_path"]).exists())
            self.assertEqual(asset["size_bytes"], len(b"fake image"))

    def test_asset_governance_reports_stats_duplicates_and_unreferenced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AetherStore(root / "aether.sqlite")
            store.init()
            referenced_path = root / "referenced.png"
            duplicate_one_path = root / "duplicate-one.png"
            duplicate_two_path = root / "duplicate-two.png"
            unreferenced_path = root / "unreferenced.png"
            for path in [referenced_path, duplicate_one_path, duplicate_two_path, unreferenced_path]:
                path.write_bytes(b"fake image")

            referenced = store.create_asset(
                {
                    "kind": "reference",
                    "source_path": str(referenced_path),
                    "asset_path": str(referenced_path),
                    "sha256": "referenced",
                    "mime_type": "image/png",
                    "size_bytes": 10,
                }
            )
            store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(duplicate_one_path),
                    "asset_path": str(duplicate_one_path),
                    "sha256": "duplicate",
                    "mime_type": "image/png",
                    "size_bytes": 20,
                }
            )
            store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(duplicate_two_path),
                    "asset_path": str(duplicate_two_path),
                    "sha256": "duplicate",
                    "mime_type": "image/png",
                    "size_bytes": 20,
                }
            )
            unreferenced = store.create_asset(
                {
                    "kind": "generated",
                    "source_path": str(unreferenced_path),
                    "asset_path": str(unreferenced_path),
                    "sha256": "unreferenced",
                    "mime_type": "image/png",
                    "size_bytes": 30,
                }
            )
            store.create_style(
                {
                    "name": "Referenced Style",
                    "source_references": [
                        {
                            "asset_id": referenced["id"],
                            "image_path": referenced["asset_path"],
                        }
                    ],
                }
            )

            stats = store.asset_stats()
            self.assertEqual(stats["total"], 4)
            self.assertEqual(stats["by_kind"]["generated"]["count"], 3)
            self.assertEqual(stats["missing_files"], 0)

            duplicates = store.duplicate_assets(kind="generated")
            self.assertEqual(len(duplicates), 1)
            self.assertEqual(duplicates[0]["sha256"], "duplicate")
            self.assertEqual(duplicates[0]["count"], 2)

            unreferenced_assets = store.unreferenced_assets(kind="generated")
            self.assertIn(unreferenced["id"], {asset["id"] for asset in unreferenced_assets})
            self.assertNotIn(referenced["id"], {asset["id"] for asset in unreferenced_assets})


if __name__ == "__main__":
    unittest.main()
