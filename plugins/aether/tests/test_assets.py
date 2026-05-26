import json
import tempfile
import unittest
from pathlib import Path

from aether_core.assets import ingest_asset
from aether_core.config import load_config


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


if __name__ == "__main__":
    unittest.main()

