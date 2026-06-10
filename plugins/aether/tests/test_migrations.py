import sqlite3
import tempfile
import unittest
from pathlib import Path

from aether_core.config import load_config
from aether_core.migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    applied_versions,
    ensure_column,
    record_schema_version,
    run_migrations,
)
from aether_core.storage import AetherStore


class MigrationFrameworkTests(unittest.TestCase):
    def test_schema_version_is_current(self):
        self.assertEqual(SCHEMA_VERSION, 7)
        self.assertEqual([version for version, _ in MIGRATIONS], [5, 6, 7])

    def test_ensure_column_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.sqlite"
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            conn.execute("create table t (a integer)")
            ensure_column(conn, "t", "b", "text not null default ''")
            ensure_column(conn, "t", "b", "text not null default ''")
            cols = {row["name"] for row in conn.execute("pragma table_info(t)").fetchall()}
            self.assertEqual(cols, {"a", "b"})

    def test_applied_versions_empty_for_uninitialised_db(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.sqlite"
            conn = sqlite3.connect(db)
            conn.execute("create table dummy (x integer)")
            conn.row_factory = sqlite3.Row
            self.assertEqual(applied_versions(conn), set())

    def test_record_schema_version_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.sqlite"
            conn = sqlite3.connect(db)
            conn.execute("create table dummy (x integer)")
            conn.row_factory = sqlite3.Row
            record_schema_version(conn, 5)
            record_schema_version(conn, 5)
            self.assertEqual(applied_versions(conn), {5})

    def _init_store(self) -> AetherStore:
        td_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(td_ctx.cleanup)
        td = td_ctx.name
        cfg_path = Path(td) / "config.json"
        cfg_path.write_text(
            '{"storage": {"databasePath": "db.sqlite", "assetRoot": "a",'
            ' "referenceImageDir": "r", "generatedImageDir": "g",'
            ' "runDir": "ru", "cacheDir": "c"}}',
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        return AetherStore(cfg.database_path)

    def test_init_lands_on_schema_version_and_is_idempotent(self):
        store = self._init_store()
        store.init()
        with store.connect() as conn:
            self.assertEqual(applied_versions(conn), {5, 6, 7})
        # Calling init() a second time must not throw and must not
        # duplicate migration rows.
        store.init()
        with store.connect() as conn:
            versions = [
                row["version"]
                for row in conn.execute(
                    "select version from schema_migrations order by version"
                ).fetchall()
            ]
            self.assertEqual(versions, [5, 6, 7])

    def test_init_after_partial_migration_picks_up_missing(self):
        store = self._init_store()
        store.init()
        # Simulate a database that was created on the pre-migration framework
        # and only has the historical v5 row recorded.
        with store.connect() as conn:
            conn.execute("delete from schema_migrations where version in (6, 7)")
            self.assertEqual(applied_versions(conn), {5})
        # init() should re-apply the missing migrations and record them.
        store.init()
        with store.connect() as conn:
            self.assertEqual(applied_versions(conn), {5, 6, 7})

    def test_business_indexes_exist_after_init(self):
        store = self._init_store()
        store.init()
        with store.connect() as conn:
            indexes = {
                row["name"]
                for row in conn.execute(
                    "select name from sqlite_master"
                    " where type='index' and name not like 'sqlite_%'"
                ).fetchall()
            }
        for required in (
            "idx_visual_assets_status_type",
            "idx_visual_asset_candidates_batch",
            "idx_visual_asset_evidence_asset",
            "idx_visual_systems_status",
            "idx_recipes_status",
            "idx_recipe_assets_recipe",
            "idx_generation_runs_source",
            "idx_assets_sha256",
        ):
            self.assertIn(required, indexes)


if __name__ == "__main__":
    unittest.main()
