from __future__ import annotations

import sqlite3

from .storage_time import now_iso


SCHEMA_VERSION = 3


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists schema_migrations (
          version integer primary key,
          applied_at text not null
        )
        """
    )


def record_schema_version(conn: sqlite3.Connection, version: int = SCHEMA_VERSION) -> None:
    ensure_migration_table(conn)
    conn.execute(
        "insert or ignore into schema_migrations (version, applied_at) values (?, ?)",
        (version, now_iso()),
    )
