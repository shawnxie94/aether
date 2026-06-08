import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aether_core.assets import ingest_asset
from aether_core.cli import _ingest_source_references
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

    def test_ingest_source_references_resolves_codex_chat_attachments(self):
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
                        }
                    }
                ),
                encoding="utf-8",
            )
            codex_home = root / "codex-home"
            session_dir = codex_home / "sessions" / "2026" / "06" / "08"
            session_dir.mkdir(parents=True)
            first_image = base64.b64encode(b"first image bytes").decode("ascii")
            second_image = base64.b64encode(b"second image bytes").decode("ascii")
            session_path = session_dir / "rollout-test.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "沉淀一下"},
                                {"type": "input_image", "image_url": f"data:image/png;base64,{first_image}"},
                                {"type": "input_image", "image_url": f"data:image/png;base64,{second_image}"},
                            ],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = load_config(config_path)
            store = AetherStore(config.database_path)
            store.init()
            payload = {
                "type": "style",
                "name": "Soft Pencil Portrait",
                "source_references": [
                    {"original_image_path": "chat_attachment:first-reference", "role": "positive_reference"},
                    {"original_image_path": "chat_attachment:second-reference", "role": "positive_reference"},
                ],
            }

            with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}):
                updated = _ingest_source_references(config, store, payload)

            references = updated["source_references"]
            self.assertEqual(references[0]["original_image_path"], "chat_attachment:first-reference")
            self.assertEqual(references[1]["original_image_path"], "chat_attachment:second-reference")
            self.assertTrue(references[0]["asset_id"].startswith("asset_"))
            self.assertTrue(references[1]["asset_id"].startswith("asset_"))
            self.assertTrue(Path(references[0]["image_path"]).exists())
            self.assertTrue(Path(references[1]["image_path"]).exists())
            self.assertNotEqual(references[0]["sha256"], references[1]["sha256"])

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
            store.create_visual_asset(
                {
                    "type": "style",
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
