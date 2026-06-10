from __future__ import annotations

import sqlite3

from .storage_time import now_iso


SCHEMA_VERSION = 7


def ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Idempotently add a column to an existing table.

    Mirrors the helper that used to live on ``AetherStore``. Centralising it
    here keeps migration functions self-contained and removes a circular
    dependency between :mod:`storage` and :mod:`migrations`.
    """
    columns = {
        row["name"]
        for row in conn.execute(f"pragma table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {definition}")


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists schema_migrations (
          version integer primary key,
          applied_at text not null
        )
        """
    )


def record_schema_version(
    conn: sqlite3.Connection, version: int = SCHEMA_VERSION
) -> None:
    ensure_migration_table(conn)
    conn.execute(
        "insert or ignore into schema_migrations (version, applied_at) values (?, ?)",
        (version, now_iso()),
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    ensure_migration_table(conn)
    return {
        row["version"]
        for row in conn.execute("select version from schema_migrations").fetchall()
    }


def _migration_v5_column_enhancements(conn: sqlite3.Connection) -> None:
    """Historical column additions prior to the explicit version list.

    These mirror the ``_ensure_column`` calls that used to live at the tail
    of ``AetherStore.init``. Keeping them as a single v5 step preserves the
    upgrade path for any database that was created before the migration
    framework existed.
    """
    ensure_column(
        conn, "prompt_records", "generation_params_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "prompt_records", "selected_assets_json", "text not null default '[]'"
    )
    ensure_column(
        conn, "prompt_records", "composition_plan_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "prompt_records", "conflicts_json", "text not null default '[]'"
    )
    ensure_column(
        conn, "prompt_records", "intent_sketch_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "prompt_records", "recall_candidates_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "prompt_records", "recall_strategy_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "generation_runs", "visual_review_json", "text not null default '{}'"
    )
    ensure_column(
        conn, "generation_runs", "selected_assets_json", "text not null default '[]'"
    )
    ensure_column(
        conn, "generation_runs", "mode", "text not null default 'generate'"
    )
    ensure_column(conn, "generation_runs", "source_generation_id", "text")
    ensure_column(conn, "generation_runs", "source_output_asset_id", "text")
    ensure_column(
        conn, "generation_runs", "edit_instruction", "text not null default ''"
    )
    ensure_column(
        conn, "generation_runs", "edit_regions_json", "text not null default '[]'"
    )
    ensure_column(
        conn, "recipes", "composition_rules_json", "text not null default '[]'"
    )
    ensure_column(conn, "recipes", "metadata_json", "text not null default '{}'")
    ensure_column(conn, "recipes", "parent_recipe_id", "text")
    ensure_column(conn, "recipes", "merged_into_recipe_id", "text")
    ensure_column(conn, "visual_systems", "parent_system_id", "text")
    ensure_column(conn, "visual_systems", "merged_into_system_id", "text")
    ensure_column(conn, "visual_asset_evidence", "source_candidate_id", "text")
    ensure_column(conn, "visual_asset_evidence", "source_reference_id", "text")


def _migration_v6_business_indexes(conn: sqlite3.Connection) -> None:
    """Add the secondary indexes that back list, recall, and evidence paths.

    The two ``embeddings`` indexes (``idx_embeddings_entity`` and
    ``idx_embeddings_model``) are still created inside the table DDL block
    in :meth:`AetherStore.init` because they are tightly coupled to the
    ``embeddings`` table definition.
    """
    # visual_assets: covers list_visual_assets (status, type) and merge-previews
    # that walk children of a parent.
    conn.execute(
        "create index if not exists idx_visual_assets_status_type "
        "on visual_assets(status, type, updated_at desc)"
    )
    conn.execute(
        "create index if not exists idx_visual_assets_parent "
        "on visual_assets(parent_asset_id) where parent_asset_id is not null"
    )
    # visual_asset_candidates: covers batch-scoped recall and confirm-batch.
    conn.execute(
        "create index if not exists idx_visual_asset_candidates_batch "
        "on visual_asset_candidates(batch_id, status, updated_at desc)"
    )
    conn.execute(
        "create index if not exists idx_visual_asset_candidates_target "
        "on visual_asset_candidates(target_asset_id) where target_asset_id is not null"
    )
    # visual_asset_evidence: covers the evidence() and quality() aggregations
    # plus the generation-run lineage queries.
    conn.execute(
        "create index if not exists idx_visual_asset_evidence_asset "
        "on visual_asset_evidence(asset_id, created_at desc)"
    )
    conn.execute(
        "create index if not exists idx_visual_asset_evidence_run "
        "on visual_asset_evidence(generation_run_id) "
        "where generation_run_id is not null"
    )
    # visual_systems / visual_system_assets / visual_system_candidates.
    conn.execute(
        "create index if not exists idx_visual_systems_status "
        "on visual_systems(status, kind, updated_at desc)"
    )
    conn.execute(
        "create index if not exists idx_visual_system_assets_system "
        "on visual_system_assets(system_id)"
    )
    conn.execute(
        "create index if not exists idx_visual_system_candidates_batch "
        "on visual_system_candidates(batch_id, status, updated_at desc)"
    )
    # recipes / recipe_assets / recipe_candidates / recipe_evidence.
    conn.execute(
        "create index if not exists idx_recipes_status "
        "on recipes(status, updated_at desc)"
    )
    conn.execute(
        "create index if not exists idx_recipe_assets_recipe "
        "on recipe_assets(recipe_id)"
    )
    conn.execute(
        "create index if not exists idx_recipe_candidates_batch "
        "on recipe_candidates(batch_id, status, updated_at desc)"
    )
    conn.execute(
        "create index if not exists idx_recipe_evidence_recipe "
        "on recipe_evidence(recipe_id, created_at desc)"
    )
    # generation_runs: covers list filters, edit-mode lineage, and stats.
    conn.execute(
        "create index if not exists idx_generation_runs_source "
        "on generation_runs(source_generation_id, created_at desc)"
    )
    conn.execute(
        "create index if not exists idx_generation_runs_status "
        "on generation_runs(status, created_at desc)"
    )
    conn.execute(
        "create index if not exists idx_generation_runs_created "
        "on generation_runs(created_at desc)"
    )
    # prompt_records: covers recent-refine and recipe-candidate recall.
    conn.execute(
        "create index if not exists idx_prompt_records_created "
        "on prompt_records(created_at desc)"
    )
    # assets: covers ingest dedupe, asset governance, and panel-data joins.
    conn.execute(
        "create index if not exists idx_assets_sha256 on assets(sha256)"
    )
    conn.execute(
        "create index if not exists idx_assets_kind on assets(kind, created_at desc)"
    )


def _migration_v7_image_fingerprints(conn: sqlite3.Connection) -> None:
    """Add the per-asset image fingerprint payload to the ``assets`` table.

    The column is JSON-typed at the application layer; the SQLite schema
    stays TEXT for portability. Existing rows will simply have ``NULL``
    until they are re-ingested, which the asset governance helpers can
    batch later if desired.
    """

    ensure_column(
        conn, "assets", "fingerprint_json", "text not null default '{}'"
    )
    conn.execute(
        "create index if not exists idx_assets_fingerprint_present "
        "on assets(sha256) where fingerprint_json != '{}'"
    )


# Ordered list of ``(schema_version, [callable])``. Each callable receives a
# connection and applies one idempotent migration step. New schema changes
# should append a new version tuple rather than editing an existing step.
MIGRATIONS: list[tuple[int, list]] = [
    (5, [_migration_v5_column_enhancements]),
    (6, [_migration_v6_business_indexes]),
    (7, [_migration_v7_image_fingerprints]),
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply every pending migration up to ``SCHEMA_VERSION``.

    Already-applied versions are skipped, so this is safe to call on every
    ``AetherStore.init``. If a future binary ships with a higher
    ``SCHEMA_VERSION`` than this module knows about, the higher version is
    only recorded when the binary's own migration list includes it.
    """
    applied = applied_versions(conn)
    for version, steps in MIGRATIONS:
        if version in applied:
            continue
        for step in steps:
            step(conn)
        record_schema_version(conn, version)
