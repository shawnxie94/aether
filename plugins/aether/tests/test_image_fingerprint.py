import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aether_core import image_fingerprint
from aether_core.assets import ingest_asset
from aether_core.config import load_config
from aether_core.recall import weighted_score
from aether_core.storage import AetherStore


class ImageFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image_path = self.root / "reference.png"
        self._write_test_image(self.image_path)

    def _write_test_image(self, path: Path) -> None:
        image = Image.new("RGB", (96, 96), (240, 235, 220))
        # warm cream background with two accent blocks: a coral square and
        # a sage rectangle. Exercises palette extraction + accent picking.
        for x in range(16, 40):
            for y in range(16, 40):
                image.putpixel((x, y), (220, 80, 70))
        for x in range(56, 88):
            for y in range(48, 80):
                image.putpixel((x, y), (130, 160, 100))
        image.save(path)

    def _config(self) -> "LoadedConfig":
        config_path = self.root / "config.json"
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
        return load_config(config_path)

    def test_compute_fingerprint_returns_palette_geometry_stats(self) -> None:
        fingerprint = image_fingerprint.compute_fingerprint(
            self.image_path, include_clip=False
        )
        self.assertEqual(fingerprint.get("schema_version"), 1)
        palette = fingerprint["palette"]
        self.assertIn("#f0ebdc", palette["dominant_hex"])
        self.assertIn("#dc5046", palette["dominant_hex"])
        self.assertIn("#82a064", palette["dominant_hex"])
        self.assertEqual(palette["temperature"], "warm")
        self.assertTrue(palette["accent_hex"])
        geometry = fingerprint["geometry"]
        self.assertEqual(geometry["width"], 96)
        self.assertEqual(geometry["height"], 96)
        self.assertEqual(geometry["aspect_ratio"], 1.0)
        self.assertEqual(len(geometry["subject_bbox"]), 4)
        stats = fingerprint["stats"]
        self.assertEqual(len(stats["stats_vector"]), 8)
        self.assertGreater(stats["edge_density"], 0.0)
        self.assertIsNone(fingerprint["clip"])

    def test_ingest_asset_persists_fingerprint(self) -> None:
        config = self._config()
        record = ingest_asset(config, self.image_path, "reference")
        self.assertIn("fingerprint", record)
        self.assertEqual(record["fingerprint"]["palette"]["dominant_hex"][0], "#f0ebdc")

        store = AetherStore(config.database_path)
        store.init()
        asset = store.create_asset(record)
        fetched = store.get_asset(asset["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(
            fetched["fingerprint"]["palette"]["dominant_hex"][0],
            "#f0ebdc",
        )

    def test_ingest_asset_can_be_disabled(self) -> None:
        config_path = self.root / "config_disabled.json"
        config_path.write_text(
            json.dumps(
                {
                    "storage": {
                        "databasePath": "aether.sqlite",
                        "assetRoot": "assets",
                        "referenceImageDir": "assets/references",
                        "generatedImageDir": "assets/generated",
                        "cacheDir": "cache",
                        "fingerprint": {"enabled": False},
                    }
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        record = ingest_asset(config, self.image_path, "reference")
        self.assertNotIn("fingerprint", record)

    def test_visual_signal_score_distinguishes_similar_and_unrelated(self) -> None:
        first = image_fingerprint.compute_fingerprint(
            self.image_path, include_clip=False
        )
        # An image that shares the cream background but otherwise has no
        # accent blocks should still get a high palette score.
        cousin_path = self.root / "cousin.png"
        cousin = Image.new("RGB", (96, 96), (240, 235, 220))
        cousin.save(cousin_path)
        cousin_fp = image_fingerprint.compute_fingerprint(
            cousin_path, include_clip=False
        )
        # And an image that is fully off-palette should score near zero.
        alien_path = self.root / "alien.png"
        alien = Image.new("RGB", (96, 96), (20, 20, 20))
        alien.save(alien_path)
        alien_fp = image_fingerprint.compute_fingerprint(
            alien_path, include_clip=False
        )
        same = image_fingerprint.visual_signal_score(first, cousin_fp)
        diff = image_fingerprint.visual_signal_score(first, alien_fp)
        self.assertGreater(same, diff)
        self.assertGreater(same, 0.15)
        self.assertLess(diff, 0.15)

    def test_weighted_score_renormalizes_when_visual_signal_present(self) -> None:
        baseline = weighted_score(
            semantic_score=0.8, lexical_score=0.5, relation_score=0.3, quality_score=0.4
        )
        boosted = weighted_score(
            semantic_score=0.8,
            lexical_score=0.5,
            relation_score=0.3,
            quality_score=0.4,
            visual_signal_score=1.0,
        )
        self.assertAlmostEqual(baseline, 0.63, places=4)
        # boosted = 0.45*0.8 + 0.20*0.5 + 0.12*0.3 + 0.05*0.4 + 0.18*1.0 = 0.85
        self.assertAlmostEqual(boosted, 0.696, places=4)
        self.assertGreater(boosted, baseline)

    def test_hybrid_recall_includes_visual_signal_score(self) -> None:
        config = self._config()
        store = AetherStore(config.database_path)
        store.init()
        warm_record = ingest_asset(config, self.image_path, "reference")
        warm_asset = store.create_asset(warm_record)
        alien_path = self.root / "alien.png"
        Image.new("RGB", (96, 96), (20, 20, 20)).save(alien_path)
        alien_record = ingest_asset(config, alien_path, "reference")
        alien_asset = store.create_asset(alien_record)

        store.create_visual_asset(
            {
                "type": "color_palette",
                "name": "Warm Cream Palette",
                "summary": "warm cream + coral + sage",
                "source_references": [
                    {
                        "image_path": warm_record["asset_path"],
                        "asset_id": warm_asset["id"],
                    }
                ],
            }
        )
        store.create_visual_asset(
            {
                "type": "color_palette",
                "name": "Shadow Palette",
                "summary": "deep shadow + dark accent",
                "source_references": [
                    {
                        "image_path": alien_record["asset_path"],
                        "asset_id": alien_asset["id"],
                    }
                ],
            }
        )

        results = store.hybrid_recall(
            "visual_asset",
            "warm pastel palette",
            query_fingerprint=warm_record["fingerprint"],
            status=None,
        )
        self.assertTrue(results)
        warm_match = next(
            (item for item in results if item["name"] == "Warm Cream Palette"), None
        )
        shadow_match = next(
            (item for item in results if item["name"] == "Shadow Palette"), None
        )
        self.assertIsNotNone(warm_match)
        self.assertIsNotNone(shadow_match)
        self.assertIn("visual_signal_score", warm_match)
        self.assertGreater(
            warm_match["visual_signal_score"], shadow_match["visual_signal_score"]
        )

    def test_canonical_text_includes_fingerprint_summary(self) -> None:
        config = self._config()
        store = AetherStore(config.database_path)
        store.init()
        record = ingest_asset(config, self.image_path, "reference")
        asset = store.create_asset(record)
        visual = store.create_visual_asset(
            {
                "type": "color_palette",
                "name": "Warm Cream Palette",
                "summary": "warm cream + coral + sage",
                "source_references": [
                    {
                        "image_path": record["asset_path"],
                        "asset_id": asset["id"],
                    }
                ],
            }
        )
        canonical = store.canonical_entity_text("visual_asset", visual)
        self.assertIn("palette hex", canonical)
        self.assertIn("temperature", canonical)
        profile = visual.get("profile") or {}
        self.assertIn("dominant_hex", profile)
        self.assertIn("accent_hex", profile)


if __name__ == "__main__":
    unittest.main()
