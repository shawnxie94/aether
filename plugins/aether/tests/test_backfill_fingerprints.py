import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from aether_core.assets import ingest_asset
from aether_core.config import load_config
from aether_core.image_fingerprint import fingerprint_path_for
from aether_core.storage import AetherStore


class BackfillFingerprintsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self._write_config()
        # Seed three assets: one with a real image, one with a missing
        # file, and one that is not image-typed.
        self.image_path = self.root / "warm.png"
        self._write_test_image(self.image_path)
        self.warm_record = ingest_asset(self.config, self.image_path, "reference")
        self.store = AetherStore(self.config.database_path)
        self.store.init()
        self.warm_asset = self.store.create_asset(self.warm_record)

        # Build a "missing on disk" asset by ingesting a real image and
        # then deleting the on-disk copy. ingest_asset validates that the
        # source file exists, so we cannot use a path that never existed.
        missing_source = self.root / "missing-source.png"
        self._write_alternate_image(missing_source)
        self.missing_record = ingest_asset(self.config, missing_source, "reference")
        missing_destination = Path(self.missing_record["asset_path"])
        assert missing_destination.exists()
        missing_destination.unlink()
        self.missing_asset = self.store.create_asset(self.missing_record)

    def _write_config(self) -> "LoadedConfig":
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

    def _write_test_image(self, path: Path) -> None:
        image = Image.new("RGB", (96, 96), (240, 235, 220))
        for x in range(16, 40):
            for y in range(16, 40):
                image.putpixel((x, y), (220, 80, 70))
        image.save(path)

    def _write_alternate_image(self, path: Path) -> None:
        # Distinct pixels so the destination filename differs from the
        # warm reference (digest-based naming dedupes identical bytes).
        image = Image.new("RGB", (96, 96), (40, 50, 90))
        for x in range(20, 60):
            for y in range(20, 60):
                image.putpixel((x, y), (10, 200, 180))
        image.save(path)

    def _clear_fingerprint(self, asset_id: str) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "update assets set fingerprint_json = '{}' where id = ?",
                (asset_id,),
            )

    def _fingerprint_json(self, asset_id: str) -> str:
        with self.store.connect() as conn:
            row = conn.execute(
                "select fingerprint_json from assets where id = ?", (asset_id,)
            ).fetchone()
        return row["fingerprint_json"]

    def test_dry_run_does_not_persist(self) -> None:
        # Force both rows into the recompute set so the plan and the
        # missing-file skip path are both exercised.
        self._clear_fingerprint(self.warm_asset["id"])
        self._clear_fingerprint(self.missing_asset["id"])
        summary = self.store.backfill_fingerprints(
            self.config, dry_run=True
        )
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(self._fingerprint_json(self.warm_asset["id"]), "{}")
        # warm record should be in the plan; missing record should be skipped
        plan_ids = {entry["asset_id"] for entry in summary["plan"]}
        self.assertIn(self.warm_asset["id"], plan_ids)
        skipped_ids = {entry["asset_id"] for entry in summary["skipped"]}
        self.assertIn(self.missing_asset["id"], skipped_ids)

    def test_only_missing_skips_already_fingerprinted_rows(self) -> None:
        # warm_asset already has a fingerprint from ingest_asset. Add a
        # second asset with no fingerprint and ensure it is the only one
        # touched.
        extra_path = self.root / "extra.png"
        self._write_test_image(extra_path)
        extra_record = ingest_asset(self.config, extra_path, "reference")
        extra_asset = self.store.create_asset(extra_record)
        self._clear_fingerprint(extra_asset["id"])

        summary = self.store.backfill_fingerprints(self.config)
        self.assertFalse(summary["dry_run"])
        self.assertEqual(summary["updated"], 1)
        plan_by_id = {entry["asset_id"]: entry for entry in summary["plan"]}
        self.assertFalse(plan_by_id[self.warm_asset["id"]]["recomputed"])
        self.assertTrue(plan_by_id[extra_asset["id"]]["recomputed"])
        # warm_asset should still hold its original fingerprint (untouched)
        warm_fp = json.loads(self._fingerprint_json(self.warm_asset["id"]))
        self.assertTrue(warm_fp.get("palette"))
        # extra_asset should now have a fingerprint
        extra_fp = json.loads(self._fingerprint_json(extra_asset["id"]))
        self.assertTrue(extra_fp.get("palette"))
        # Sidecar files should be in place for every successful backfill
        self.assertTrue(Path(fingerprint_path_for(extra_record["asset_path"])).exists())

    def test_all_flag_recomputes_existing_fingerprints(self) -> None:
        original_fp = json.loads(self._fingerprint_json(self.warm_asset["id"]))
        # Force a stale fingerprint that differs from what recompute
        # would produce so we can detect the write.
        stale = {"schema_version": 1, "palette": {"dominant_hex": ["#000000"]}}
        self.store.update_asset_fingerprint(self.warm_asset["id"], stale)
        self.assertEqual(
            json.loads(self._fingerprint_json(self.warm_asset["id"])),
            stale,
        )
        summary = self.store.backfill_fingerprints(self.config, only_missing=False)
        self.assertEqual(summary["updated"], 1)
        refreshed = json.loads(self._fingerprint_json(self.warm_asset["id"]))
        self.assertNotEqual(refreshed, stale)
        # We may or may not have hit the original colors exactly, but
        # the recompute always populates the real palette block.
        self.assertTrue(refreshed.get("palette", {}).get("dominant_hex"))
        # Sanity: the recomputed value should match the original ingest.
        self.assertEqual(
            refreshed["palette"]["dominant_hex"],
            original_fp["palette"]["dominant_hex"],
        )

    def test_missing_file_is_skipped_not_failed(self) -> None:
        # Force the missing file into the recompute set by clearing its
        # fingerprint first.
        self._clear_fingerprint(self.missing_asset["id"])
        summary = self.store.backfill_fingerprints(
            self.config, only_kinds=["reference"]
        )
        skipped_ids = {entry["asset_id"] for entry in summary["skipped"]}
        self.assertIn(self.missing_asset["id"], skipped_ids)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["failed"], [])

    def test_persist_failure_is_recorded_in_failed(self) -> None:
        self._clear_fingerprint(self.warm_asset["id"])
        with patch.object(
            self.store, "update_asset_fingerprint", side_effect=RuntimeError("boom")
        ):
            summary = self.store.backfill_fingerprints(self.config)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(len(summary["failed"]), 1)
        self.assertIn("boom", summary["failed"][0]["reason"])
        self.assertEqual(summary["failed"][0]["asset_id"], self.warm_asset["id"])

    def test_kind_filter_restricts_scan(self) -> None:
        self._clear_fingerprint(self.warm_asset["id"])
        summary_only_reference = self.store.backfill_fingerprints(
            self.config, kind="reference"
        )
        plan_ids = {entry["asset_id"] for entry in summary_only_reference["plan"]}
        self.assertIn(self.warm_asset["id"], plan_ids)
        summary_only_generated = self.store.backfill_fingerprints(
            self.config, kind="generated"
        )
        self.assertEqual(summary_only_generated["scanned"], 0)


if __name__ == "__main__":
    unittest.main()
