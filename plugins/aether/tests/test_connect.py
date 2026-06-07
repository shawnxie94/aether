import sqlite3
import tempfile
import unittest
import warnings
from pathlib import Path

from aether_core.config import load_config
from aether_core.storage import AetherStore


class ConnectContextManagerTests(unittest.TestCase):
    """``AetherStore.connect()`` is a generator-based context manager.

    CPython 3.14 changed ``sqlite3.Connection.close()`` to roll back pending
    transactions instead of auto-committing them. The original
    ``connect()`` relied on ``Connection.__exit__`` (which still commits
    then closes), so this regression test pins down the new contract: a
    successful ``with`` block commits, a raising one rolls back.
    """

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

    def test_with_block_commits_writes(self):
        store = self._init_store()
        store.init()
        with store.connect() as conn:
            conn.execute(
                "insert into assets (id, kind, source_path, asset_path,"
                " sha256, mime_type, size_bytes, created_at)"
                " values (?, ?, ?, ?, ?, ?, 0, ?)",
                ("a1", "reference", "/x", "/x", "sha", "image/png", "2024-01-01T00:00:00"),
            )
        with store.connect() as conn:
            rows = conn.execute("select id from assets").fetchall()
        self.assertEqual([r[0] for r in rows], ["a1"])

    def test_exception_inside_with_block_rolls_back(self):
        store = self._init_store()
        store.init()
        with self.assertRaises(RuntimeError):
            with store.connect() as conn:
                conn.execute(
                    "insert into assets (id, kind, source_path, asset_path,"
                    " sha256, mime_type, size_bytes, created_at)"
                    " values (?, ?, ?, ?, ?, ?, 0, ?)",
                    ("a2", "reference", "/x", "/x", "sha", "image/png", "2024-01-01T00:00:00"),
                )
                raise RuntimeError("simulated failure")
        with store.connect() as conn:
            rows = conn.execute("select id from assets").fetchall()
        self.assertEqual(rows, [])

    def test_no_unclosed_database_warning_on_clean_use(self):
        store = self._init_store()
        store.init()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with store.connect() as conn:
                conn.execute("select 1").fetchall()
        leak_warnings = [
            w
            for w in caught
            if issubclass(w.category, ResourceWarning)
            and "unclosed database" in str(w.message)
        ]
        self.assertEqual(
            leak_warnings,
            [],
            "connect() leaked a database connection",
        )

    def test_close_after_with_is_safe(self):
        """Calling ``conn.close()`` inside the with-block should not blow up."""
        store = self._init_store()
        store.init()
        with store.connect() as conn:
            conn.close()
            # The next call would normally raise on a closed connection; we
            # just want to confirm the contextmanager's finally doesn't
            # raise ``ProgrammingError`` when the connection is already
            # closed.
        # Open a fresh connection to confirm the DB is still usable.
        with store.connect() as conn:
            self.assertEqual(conn.execute("select 1").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
