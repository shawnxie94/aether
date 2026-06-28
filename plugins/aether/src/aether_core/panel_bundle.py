from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .assets import asset_dir_for_kind
from .config import LoadedConfig, ensure_configured_dirs
from .storage import AetherStore


BUNDLE_FORMAT = "aether-panel-bundle"
BUNDLE_VERSION = 1
BUNDLE_TABLES = [
    "assets",
    "visual_assets",
    "visual_asset_candidates",
    "visual_asset_evidence",
    "visual_asset_revisions",
    "visual_systems",
    "visual_system_assets",
    "visual_system_candidates",
    "visual_system_evidence",
    "visual_system_revisions",
    "recipes",
    "recipe_assets",
    "recipe_candidates",
    "recipe_evidence",
    "recipe_revisions",
    "prompt_records",
    "generation_runs",
    "panel_favorites",
]
REPLACE_CLEAR_TABLES = ["embeddings"]


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _table_rows(store: AetherStore, table: str) -> list[dict[str, Any]]:
    with store.connect() as conn:
        rows = conn.execute(f"select * from {table}").fetchall()
    return [dict(row) for row in rows]


def _table_columns(conn: Any, table: str) -> set[str]:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _asset_suffix(asset: dict[str, Any]) -> str:
    path_suffix = Path(asset.get("asset_path") or asset.get("source_path") or "").suffix
    if path_suffix:
        return path_suffix
    guessed = mimetypes.guess_extension(asset.get("mime_type") or "")
    return guessed or ".bin"


def _bundle_asset_path(asset: dict[str, Any]) -> str:
    return f"files/assets/{asset['id']}{_asset_suffix(asset)}"


def export_panel_bundle(config: LoadedConfig, store: AetherStore) -> tuple[bytes, str]:
    records = {table: _table_rows(store, table) for table in BUNDLE_TABLES}
    asset_files: dict[str, dict[str, Any]] = {}
    buffer = BytesIO()

    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for asset in records["assets"]:
            asset_path = Path(asset.get("asset_path") or "")
            if not asset_path.exists() or not asset_path.is_file():
                continue
            bundle_path = _bundle_asset_path(asset)
            archive.write(asset_path, bundle_path)
            asset_files[asset["id"]] = {
                "path": bundle_path,
                "size_bytes": asset_path.stat().st_size,
                "sha256": asset.get("sha256", ""),
            }

        manifest = {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "project": config.data.get("project", {}),
            "records": records,
            "asset_files": asset_files,
            "counts": {table: len(rows) for table, rows in records.items()},
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return buffer.getvalue(), f"aether-panel-bundle-{_now_slug()}.zip"


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("format") != BUNDLE_FORMAT:
        raise ValueError("Unsupported bundle format")
    if int(manifest.get("version") or 0) > BUNDLE_VERSION:
        raise ValueError("Bundle version is newer than this Aether panel supports")
    if not isinstance(manifest.get("records"), dict):
        raise ValueError("Bundle manifest is missing records")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rewrite_paths(value: Any, path_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_paths(item, path_map) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_paths(item, path_map) for item in value]
    if isinstance(value, str):
        updated = value
        for old_path, new_path in path_map.items():
            updated = updated.replace(old_path, new_path)
        return updated
    return value


def _copy_asset_file(
    archive: ZipFile,
    asset: dict[str, Any],
    file_meta: dict[str, Any],
    config: LoadedConfig,
) -> tuple[dict[str, Any], dict[str, str]]:
    bundle_path = file_meta.get("path")
    if not isinstance(bundle_path, str) or bundle_path not in archive.namelist():
        return asset, {}

    data = archive.read(bundle_path)
    digest = _sha256_bytes(data)
    destination_dir = asset_dir_for_kind(config, asset["kind"])
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{digest[:16]}{_asset_suffix(asset)}"
    if not destination.exists():
        destination.write_bytes(data)

    updated = dict(asset)
    path_map = {}
    for key in ("asset_path", "source_path"):
        old_path = updated.get(key)
        if isinstance(old_path, str) and old_path:
            path_map[old_path] = str(destination)
        updated[key] = str(destination)
    updated["sha256"] = digest
    updated["size_bytes"] = destination.stat().st_size
    return updated, path_map


def _insert_rows(conn: Any, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    allowed_columns = _table_columns(conn, table)
    columns = [column for column in rows[0].keys() if column in allowed_columns]
    if not columns:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    sql = f"insert or replace into {table} ({column_sql}) values ({placeholders})"
    conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
    return len(rows)


def import_panel_bundle(config: LoadedConfig, store: AetherStore, bundle: bytes, *, mode: str = "merge") -> dict[str, Any]:
    if mode not in {"merge", "replace"}:
        raise ValueError("Import mode must be merge or replace")
    ensure_configured_dirs(config)

    try:
        archive = ZipFile(BytesIO(bundle))
    except BadZipFile as error:
        raise ValueError("Invalid Aether bundle zip") from error

    with archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except KeyError as error:
            raise ValueError("Bundle is missing manifest.json") from error
        _validate_manifest(manifest)

        records = manifest["records"]
        asset_files = manifest.get("asset_files", {})
        path_map: dict[str, str] = {}
        prepared_records: dict[str, list[dict[str, Any]]] = {}

        for table in BUNDLE_TABLES:
            table_rows = records.get(table, [])
            if not isinstance(table_rows, list):
                raise ValueError(f"Bundle table is invalid: {table}")
            prepared_records[table] = [dict(row) for row in table_rows if isinstance(row, dict)]

        imported_assets = []
        for asset in prepared_records["assets"]:
            updated_asset, updated_paths = _copy_asset_file(
                archive,
                asset,
                asset_files.get(asset.get("id"), {}) if isinstance(asset_files, dict) else {},
                config,
            )
            path_map.update(updated_paths)
            imported_assets.append(updated_asset)
        prepared_records["assets"] = imported_assets

        if path_map:
            for table, rows in prepared_records.items():
                prepared_records[table] = [_rewrite_paths(row, path_map) for row in rows]

        with store.connect() as conn:
            if mode == "replace":
                for table in REPLACE_CLEAR_TABLES:
                    conn.execute(f"delete from {table}")
                for table in reversed(BUNDLE_TABLES):
                    conn.execute(f"delete from {table}")
            counts = {
                table: _insert_rows(conn, table, rows)
                for table, rows in prepared_records.items()
            }
        try:
            from .panel_data import invalidate_panel_lookup_cache

            invalidate_panel_lookup_cache()
        except Exception:
            pass

    return {
        "ok": True,
        "mode": mode,
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "counts": counts,
        "asset_file_count": len([asset for asset in prepared_records["assets"] if asset.get("asset_path")]),
    }
