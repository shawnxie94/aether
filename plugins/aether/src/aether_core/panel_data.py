from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from pathlib import Path
from typing import Any

from .config import LoadedConfig
from .storage import AetherStore


def _selected_asset_id(selected: Any) -> str:
    if isinstance(selected, str):
        return selected
    if isinstance(selected, dict):
        value = selected.get("asset_id") or selected.get("id")
        return value if isinstance(value, str) else ""
    return ""


def _first_output_asset_id(output: Any) -> str:
    if isinstance(output, dict):
        value = output.get("asset_id") or output.get("id")
        return value if isinstance(value, str) else ""
    return ""


def _image_from_asset(asset: dict[str, Any]) -> dict[str, Any]:
    # The panel only uses ``exists`` to filter missing images; the
    # frontend treats ``exists !== false`` as visible, so we leave the
    # field ``True`` and skip the synchronous ``path.exists()`` stat per
    # image. Any real miss will surface as a broken image the moment the
    # browser tries to fetch ``/asset/<id>``.
    path = Path(asset.get("asset_path", ""))
    return {
        "id": asset["id"],
        "kind": asset["kind"],
        "src": f"/asset/{asset['id']}",
        "label": path.name or asset["id"],
        "sha256": asset.get("sha256", ""),
        "size_bytes": asset.get("size_bytes", 0),
        "exists": True,
        "fingerprint": _panel_image_fingerprint(asset.get("fingerprint") or {}),
    }


def _panel_image_fingerprint(fingerprint: dict[str, Any]) -> dict[str, Any]:
    """Project the raw image fingerprint into the lightweight shape the
    panel renders. Keeps only the palette / geometry / stats blocks the
    UI cares about, plus a ``has_clip`` boolean so the template can show
    whether the embedding is present without leaking the vector.
    """
    if not fingerprint:
        return {}
    palette = fingerprint.get("palette") or {}
    geometry = fingerprint.get("geometry") or {}
    stats = fingerprint.get("stats") or {}
    if not (palette or geometry or stats):
        return {}
    summary: dict[str, Any] = {"has_clip": bool(fingerprint.get("clip"))}
    if palette:
        summary["palette"] = {
            "dominant_hex": palette.get("dominant_hex") or [],
            "accent_hex": palette.get("accent_hex") or [],
            "temperature": palette.get("temperature"),
            "saturation": palette.get("saturation"),
        }
    if geometry:
        summary["geometry"] = {
            "width": geometry.get("width"),
            "height": geometry.get("height"),
            "aspect_ratio": geometry.get("aspect_ratio"),
        }
    if stats:
        summary["stats"] = {
            "mean_brightness": stats.get("mean_brightness"),
            "contrast": stats.get("contrast"),
        }
    return summary


def _visual_asset_image_fingerprint(asset: dict[str, Any]) -> dict[str, Any]:
    """Return the visual asset level ``image_fingerprint`` snapshot.

    The snapshot is already merged into ``asset["profile"]`` by
    :meth:`AetherStore._merge_image_fingerprint_into_profile`, so the
    panel renderer can read it directly from the profile payload.
    """
    profile = asset.get("profile") or {}
    snapshot = profile.get("image_fingerprint")
    return snapshot if isinstance(snapshot, dict) else {}


def _compact_text(value: str, limit: int = 180) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "..."


def _resolve_images(asset_ids: list[str], asset_map: dict[str, dict[str, Any]], kind: str | None = None) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    images: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        if asset_id in seen_ids:
            continue
        seen_ids.add(asset_id)
        asset = asset_map.get(asset_id)
        if not asset:
            continue
        if kind and asset.get("kind") != kind:
            continue
        image = _image_from_asset(asset)
        fingerprint = _image_fingerprint(image)
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        images.append(image)
    return images


def _image_fingerprint(image: dict[str, Any]) -> str:
    sha256 = image.get("sha256")
    if isinstance(sha256, str) and sha256:
        return f"sha256:{sha256}"
    return f"fallback:{image.get('kind', '')}:{image.get('label', '')}:{image.get('size_bytes', 0)}"


def _merge_images(*image_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    images: list[dict[str, Any]] = []
    for group in image_groups:
        for image in group:
            fingerprint = _image_fingerprint(image)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            images.append(image)
    return images


def _reference_ids_from_visual_asset(asset: dict[str, Any], path_to_asset_id: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for reference in asset.get("source_references", []):
        if not isinstance(reference, dict):
            continue
        asset_id = reference.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            ids.append(asset_id)
            continue
        for key in ("asset_path", "image_path"):
            path = reference.get(key)
            if isinstance(path, str) and path in path_to_asset_id:
                ids.append(path_to_asset_id[path])
                break
    return ids


def collect_panel_data(config: LoadedConfig, store: AetherStore) -> dict[str, Any]:
    assets = store.list_assets(limit=None)
    asset_map = {asset["id"]: asset for asset in assets}
    path_to_asset_id = {asset["asset_path"]: asset["id"] for asset in assets}
    visual_assets = store.list_visual_assets(limit=None)
    systems = store.list_visual_systems(limit=None)
    recipes = store.list_recipes(limit=None)
    generations = store.list_generation_runs(limit=None)
    favorite_rows = store.list_panel_favorites()
    favorite_keys = {(row["entity_type"], row["entity_id"]) for row in favorite_rows}
    favorite_created_at = {(row["entity_type"], row["entity_id"]): row["created_at"] for row in favorite_rows}

    generated_by_visual_asset: dict[str, list[str]] = {}
    for run in generations:
        output_ids = [_first_output_asset_id(output) for output in run.get("outputs", [])]
        output_ids = [asset_id for asset_id in output_ids if asset_id]
        if not output_ids:
            continue
        for selected in run.get("selected_assets", []):
            selected_id = _selected_asset_id(selected)
            if not selected_id:
                continue
            generated_by_visual_asset.setdefault(selected_id, [])
            generated_by_visual_asset[selected_id].extend(output_ids)

    visual_asset_by_id = {asset["id"]: asset for asset in visual_assets}
    system_by_id = {system["id"]: system for system in systems}
    visual_asset_items: list[dict[str, Any]] = []
    for asset in visual_assets:
        reference_ids = _reference_ids_from_visual_asset(asset, path_to_asset_id)
        generated_ids = generated_by_visual_asset.get(asset["id"], [])
        visual_asset_items.append(
            {
                "id": asset["id"],
                "type": asset["type"],
                "name": asset["name"],
                "summary": _compact_text(asset.get("summary", "")),
                "tags": asset.get("tags", []),
                "status": asset["status"],
                "updated_at": asset["updated_at"],
                "profile": asset.get("profile", {}),
                "prompt_fragments": asset.get("prompt_fragments", []),
                "negative_fragments": asset.get("negative_fragments", []),
                "compatible_with": asset.get("compatible_with", []),
                "avoid_with": asset.get("avoid_with", []),
                "prompt_fragment_count": len(asset.get("prompt_fragments", [])),
                "negative_fragment_count": len(asset.get("negative_fragments", [])),
                "reference_images": _resolve_images(reference_ids, asset_map, kind="reference"),
                "generated_images": _resolve_images(generated_ids, asset_map, kind="generated"),
                "image_fingerprint": _visual_asset_image_fingerprint(asset),
            }
        )

    system_items: list[dict[str, Any]] = []
    for system in systems:
        reference_ids = [asset_id for asset_id in system.get("source_reference_ids", []) if isinstance(asset_id, str)]
        direct_images = _resolve_images(reference_ids, asset_map)
        system_assets = store.list_visual_system_assets(system_id=system["id"])
        related_assets = [
            {
                "id": relation["asset_id"],
                "role": relation.get("role", "optional"),
                "weight": relation.get("weight", 0),
                "reason": relation.get("reason", ""),
                "name": visual_asset_by_id.get(relation["asset_id"], {}).get("name", relation["asset_id"]),
                "type": visual_asset_by_id.get(relation["asset_id"], {}).get("type", ""),
                "summary": visual_asset_by_id.get(relation["asset_id"], {}).get("summary", ""),
                "status": visual_asset_by_id.get(relation["asset_id"], {}).get("status", ""),
            }
            for relation in system_assets
        ]
        related_generated_ids: list[str] = []
        for relation in system_assets:
            related_generated_ids.extend(generated_by_visual_asset.get(relation["asset_id"], []))
        direct_reference_images = [image for image in direct_images if image["kind"] == "reference"]
        direct_generated_images = [image for image in direct_images if image["kind"] == "generated"]
        related_generated_images = _resolve_images(related_generated_ids, asset_map, kind="generated")
        system_items.append(
            {
                "id": system["id"],
                "kind": system["kind"],
                "name": system["name"],
                "summary": _compact_text(system.get("summary", "")),
                "definition": system.get("summary", ""),
                "tags": system.get("tags", []),
                "visual_rules": system.get("visual_rules", []),
                "avoid_rules": system.get("avoid_rules", []),
                "status": system["status"],
                "updated_at": system["updated_at"],
                "entity_type": "visual_system",
                "source_view": "visual_systems",
                "is_favorite": ("visual_system", system["id"]) in favorite_keys,
                "favorite_at": favorite_created_at.get(("visual_system", system["id"])),
                "related_assets": related_assets,
                "reference_images": direct_reference_images,
                "generated_images": _merge_images(direct_generated_images, related_generated_images),
            }
        )

    recipe_items: list[dict[str, Any]] = []
    for recipe in recipes:
        reference_ids = [asset_id for asset_id in recipe.get("source_reference_ids", []) if isinstance(asset_id, str)]
        direct_images = _resolve_images(reference_ids, asset_map)
        recipe_assets = store.list_recipe_assets(recipe_id=recipe["id"])
        related_assets = [
            {
                "id": relation["asset_id"],
                "role": relation.get("role", "optional"),
                "weight": relation.get("weight", 0),
                "reason": relation.get("reason", ""),
                "name": visual_asset_by_id.get(relation["asset_id"], {}).get("name", relation["asset_id"]),
                "type": visual_asset_by_id.get(relation["asset_id"], {}).get("type", ""),
                "summary": visual_asset_by_id.get(relation["asset_id"], {}).get("summary", ""),
                "status": visual_asset_by_id.get(relation["asset_id"], {}).get("status", ""),
            }
            for relation in recipe_assets
        ]
        related_generated_ids = []
        for relation in recipe_assets:
            related_generated_ids.extend(generated_by_visual_asset.get(relation["asset_id"], []))
        parent_systems = [
            {
                "id": system_id,
                "name": system_by_id.get(system_id, {}).get("name", system_id),
                "kind": system_by_id.get(system_id, {}).get("kind", ""),
                "status": system_by_id.get(system_id, {}).get("status", ""),
            }
            for system_id in recipe.get("parent_system_ids", [])
            if isinstance(system_id, str)
        ]
        direct_reference_images = [image for image in direct_images if image["kind"] == "reference"]
        direct_generated_images = [image for image in direct_images if image["kind"] == "generated"]
        related_generated_images = _resolve_images(related_generated_ids, asset_map, kind="generated")
        recipe_items.append(
            {
                "id": recipe["id"],
                "name": recipe["name"],
                "summary": _compact_text(recipe.get("summary", "")),
                "definition": recipe.get("summary", ""),
                "status": recipe["status"],
                "source": recipe.get("source", ""),
                "reason": recipe.get("reason", ""),
                "updated_at": recipe["updated_at"],
                "entity_type": "recipe",
                "source_view": "recipes",
                "is_favorite": ("recipe", recipe["id"]) in favorite_keys,
                "favorite_at": favorite_created_at.get(("recipe", recipe["id"])),
                "parent_systems": parent_systems,
                "use_cases": recipe.get("use_cases", []),
                "required_asset_types": recipe.get("required_asset_types", []),
                "composition_rules": recipe.get("composition_rules", []),
                "recommended_aspect_ratios": recipe.get("recommended_aspect_ratios", []),
                "confidence": recipe.get("confidence"),
                "related_assets": related_assets,
                "reference_images": direct_reference_images,
                "generated_images": _merge_images(direct_generated_images, related_generated_images),
            }
        )

    file_items = [_image_from_asset(asset) for asset in assets]
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for asset in visual_asset_items:
        type_counts[asset["type"]] = type_counts.get(asset["type"], 0) + 1
        status_counts[asset["status"]] = status_counts.get(asset["status"], 0) + 1
    favorites = [
        item
        for item in [*recipe_items, *system_items]
        if item.get("is_favorite")
    ]
    favorites.sort(key=lambda item: item.get("favorite_at") or item.get("updated_at") or "", reverse=True)

    return {
        "project": config.data.get("project", {}),
        "database_path": str(config.database_path),
        "storage": {
            "asset_root": str(config.resolve_path(config.data["storage"]["assetRoot"])),
            "reference_dir": str(config.resolve_path(config.data["storage"]["referenceImageDir"])),
            "generated_dir": str(config.resolve_path(config.data["storage"]["generatedImageDir"])),
        },
        "summary": {
            "visual_asset_count": len(visual_asset_items),
            "visual_system_count": len(system_items),
            "recipe_count": len(recipe_items),
            "reference_file_count": len([asset for asset in assets if asset["kind"] == "reference"]),
            "generated_file_count": len([asset for asset in assets if asset["kind"] == "generated"]),
            "generation_count": len(generations),
            "favorite_count": len(favorites),
            "asset_type_counts": type_counts,
            "asset_status_counts": status_counts,
        },
        "visual_assets": visual_asset_items,
        "visual_systems": system_items,
        "recipes": recipe_items,
        "favorites": favorites,
        "files": file_items,
    }


# In-memory memo of the per-section ETag tuples. ETag values only
# change when the underlying tables mutate, so caching the result of
# ``_section_etag_values`` for a short window lets the per-section
# collector endpoints reuse the same (max_updated_at, count) snapshot
# across a single parallel batch without paying for 5 ``max() + count()``
# SQL queries per request.
_ETAG_TTL_SECONDS = 1.0
_etag_cache: dict[str, tuple[str, int]] | None = None
_etag_cache_expires_at: float = 0.0
_etag_cache_lock = threading.Lock()


def _section_etag_values(store: AetherStore) -> dict[str, tuple[str, int]]:
    """Return a small set of (max_updated_at, count) tuples per panel section.

    Used to compute a stable ETag without re-walking the full visual
    memory. The values are cheap to fetch (one ``max(updated_at)`` and one
    ``count(*)`` per table) and they change exactly when the panel data
    for that section would change. Hashing them gives a per-section
    strong ETag.
    """
    sections: dict[str, tuple[str, int]] = {}
    # Some tables (notably ``panel_favorites``) use ``created_at`` rather
    # than ``updated_at``. Look up the timestamp column per table to keep
    # the ETag computation in one place.
    timestamp_columns: dict[str, str] = {
        "visual_assets": "updated_at",
        "visual_systems": "updated_at",
        "recipes": "updated_at",
        "generation_runs": "created_at",
        "panel_favorites": "created_at",
    }
    global _etag_cache, _etag_cache_expires_at
    now = time.monotonic()
    cached = _etag_cache
    if cached is not None and now < _etag_cache_expires_at:
        return cached
    with _etag_cache_lock:
        if _etag_cache is not None and now < _etag_cache_expires_at:
            return _etag_cache
        with store.connect() as conn:
            for label, table in (
                ("visual_assets", "visual_assets"),
                ("visual_systems", "visual_systems"),
                ("recipes", "recipes"),
                ("generations", "generation_runs"),
                ("favorites", "panel_favorites"),
            ):
                column = timestamp_columns[table]
                row = conn.execute(
                    f"select coalesce(max({column}), '') as ts, count(*) as n"
                    f" from {table}"
                ).fetchone()
                sections[label] = (row["ts"], int(row["n"]))
        _etag_cache = sections
        _etag_cache_expires_at = time.monotonic() + _ETAG_TTL_SECONDS
    return sections


def panel_etag(store: AetherStore, sections: list[str] | None = None) -> str:
    """Compute a strong ETag covering the requested panel sections.

    ``sections`` is an ordered list of section names. Different endpoints
    want different sections, so they pass only what they need:

    - ``["summary"]`` covers counts and type breakdowns
    - ``["visual_assets"]`` covers the visual asset list
    - ``["visual_systems"]`` covers the visual system list
    - ``["recipes"]`` covers the recipe list
    - ``["favorites"]`` covers the favorites list

    The combined ETag is the SHA-256 hex digest of the per-section
    (max_updated_at, count) pairs in order.
    """
    wanted = sections or ["visual_assets", "visual_systems", "recipes", "favorites", "generations"]
    values = _section_etag_values(store)
    h = hashlib.sha256()
    for label in wanted:
        ts, count = values.get(label, ("", 0))
        h.update(label.encode("utf-8"))
        h.update(b"\x00")
        h.update(ts.encode("utf-8"))
        h.update(b"\x00")
        h.update(str(count).encode("utf-8"))
        h.update(b"\x1f")
    return f'"{h.hexdigest()}"'


def collect_panel_summary(config: LoadedConfig, store: AetherStore) -> dict[str, Any]:
    """Return just the ``summary`` block from :func:`collect_panel_data`.

    Much cheaper than the full panel payload because it does not walk the
    individual visual asset / system / recipe rows. Used by
    ``/api/panel-data/summary`` so the panel can poll counts every few
    seconds without paying the full-walk cost.

    Reads from the shared :func:`_gather_lookup_tables` cache so the
    summary and the per-section collectors triggered by the same page
    open only walk the underlying tables once.
    """
    lookups = _gather_lookup_tables(store)
    visual_assets = lookups["visual_assets"]
    systems = lookups["systems"]
    recipes = lookups["recipes"]
    generations = lookups["generations"]
    favorite_rows = lookups["favorite_rows"]
    assets = list(lookups["asset_map"].values())
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for asset in visual_assets:
        type_counts[asset["type"]] = type_counts.get(asset["type"], 0) + 1
        status_counts[asset["status"]] = status_counts.get(asset["status"], 0) + 1
    return {
        "project": config.data.get("project", {}),
        "database_path": str(config.database_path),
        "storage": {
            "asset_root": str(config.resolve_path(config.data["storage"]["assetRoot"])),
            "reference_dir": str(config.resolve_path(config.data["storage"]["referenceImageDir"])),
            "generated_dir": str(config.resolve_path(config.data["storage"]["generatedImageDir"])),
        },
        "summary": {
            "visual_asset_count": len(visual_assets),
            "visual_system_count": len(systems),
            "recipe_count": len(recipes),
            "reference_file_count": len([a for a in assets if a["kind"] == "reference"]),
            "generated_file_count": len([a for a in assets if a["kind"] == "generated"]),
            "generation_count": len(generations),
            "favorite_count": len(favorite_rows),
            "asset_type_counts": type_counts,
            "asset_status_counts": status_counts,
        },
    }


def collect_panel_visual_assets(config: LoadedConfig, store: AetherStore) -> list[dict[str, Any]]:
    """Return just the visual asset items from :func:`collect_panel_data`.

    Reads from the shared lookup cache so the visual-asset section
    does not redo the full assets / visual_assets / generations walks
    when another section in the same batch has already paid for them.
    """
    lookups = _gather_lookup_tables(store)
    asset_map = lookups["asset_map"]
    path_to_asset_id = lookups["path_to_asset_id"]
    visual_assets = lookups["visual_assets"]
    generated_by_visual_asset = lookups["generated_by_visual_asset"]
    items: list[dict[str, Any]] = []
    for asset in visual_assets:
        reference_ids = _reference_ids_from_visual_asset(asset, path_to_asset_id)
        generated_ids = generated_by_visual_asset.get(asset["id"], [])
        items.append(
            {
                "id": asset["id"],
                "type": asset["type"],
                "name": asset["name"],
                "summary": _compact_text(asset.get("summary", "")),
                "tags": asset.get("tags", []),
                "status": asset["status"],
                "updated_at": asset["updated_at"],
                "profile": asset.get("profile", {}),
                "prompt_fragments": asset.get("prompt_fragments", []),
                "negative_fragments": asset.get("negative_fragments", []),
                "compatible_with": asset.get("compatible_with", []),
                "avoid_with": asset.get("avoid_with", []),
                "prompt_fragment_count": len(asset.get("prompt_fragments", [])),
                "negative_fragment_count": len(asset.get("negative_fragments", [])),
                "reference_images": _resolve_images(reference_ids, asset_map, kind="reference"),
                "generated_images": _resolve_images(generated_ids, asset_map, kind="generated"),
                "image_fingerprint": _visual_asset_image_fingerprint(asset),
            }
        )
    return items


def _generated_outputs_by_visual_asset(
    visual_assets: list[dict[str, Any]],
    generations: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Build a ``visual_asset_id -> [generated_output_asset_id]`` map.

    Used by the visual_system and recipe item builders to attach the
    ``generated_images`` array without re-walking the full generation
    table per entity. Returns ``(map, visual_asset_by_id)`` because
    every caller also needs the visual asset lookup table.

    ``visual_assets`` and ``generations`` are passed in (rather than
    fetched here) so the per-section collectors can share a single
    pair of full-table scans via :func:`_gather_lookup_tables`.
    """
    visual_asset_by_id = {asset["id"]: asset for asset in visual_assets}
    generated_by_visual_asset: dict[str, list[str]] = {}
    for run in generations:
        output_ids = [
            (output.get("asset_id") or output.get("id"))
            for output in run.get("outputs", [])
            if isinstance(output, dict)
            and (output.get("asset_id") or output.get("id"))
        ]
        if not output_ids:
            continue
        for selected in run.get("selected_assets", []):
            selected_id = _selected_asset_id(selected)
            if not selected_id:
                continue
            generated_by_visual_asset.setdefault(selected_id, []).extend(output_ids)
    return generated_by_visual_asset, visual_asset_by_id


# Module-level memo of the per-section lookup tables. Each entry lives
# for ``_LOOKUP_TTL_SECONDS`` so the four per-section collectors (which
# typically fire as a single parallel batch from the panel) all share
# one round of full-table walks. Writes call
# :func:`invalidate_panel_lookup_cache` to drop the cache eagerly.
_LOOKUP_TTL_SECONDS = 1.0
_panel_lookup_cache: dict[str, Any] | None = None
_panel_lookup_expires_at: float = 0.0
_panel_lookup_lock = threading.Lock()


def invalidate_panel_lookup_cache() -> None:
    """Drop the shared panel lookup cache. Call after any write that
    mutates the underlying tables the panel renders from."""
    global _panel_lookup_cache, _panel_lookup_expires_at
    with _panel_lookup_lock:
        _panel_lookup_cache = None
        _panel_lookup_expires_at = 0.0


# Tracks an in-progress fill so a burst of concurrent section
# requests triggered by a single page open only pays the full-table
# walk once. The first caller becomes the filler; the rest wait on
# ``_panel_lookup_filled`` and read the freshly populated cache.
_panel_lookup_filled: threading.Event = threading.Event()


# Reused across fills so we do not pay thread-pool startup cost on
# every page open. The pool is sized to the number of tables we
# fan out; bumping it higher would not help because sqlite is the
# bottleneck, not Python scheduling.
_PANEL_FILL_POOL: ThreadPoolExecutor | None = None


def _fill_pool() -> ThreadPoolExecutor:
    global _PANEL_FILL_POOL
    if _PANEL_FILL_POOL is None:
        _PANEL_FILL_POOL = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="aether-panel-fill"
        )
    return _PANEL_FILL_POOL


def _fill_lookup_tables(store: AetherStore) -> dict[str, Any]:
    """Do the actual full-table scans and write the result into the cache.

    Runs under ``_panel_lookup_lock`` so two concurrent fillers never
    walk the tables in parallel (which would defeat the point of the
    cache). All other callers wait on ``_panel_lookup_filled`` in
    :func:`_gather_lookup_tables`.

    The eight ``list_*`` calls each open their own sqlite connection
    and walk a full table. The total work is bounded by the slowest
    single scan, not their sum, because the scans are submitted to a
    thread pool and sqlite serialises the connections anyway. This
    cuts the cold fill wall time roughly in half on the production
    24MB database.
    """
    global _panel_lookup_cache, _panel_lookup_expires_at
    pool = _fill_pool()
    # Submit the assets and visual_assets walks as a coordinated pair:
    # ``list_visual_assets`` would otherwise fire an N+1 ``get_asset``
    # per source-reference during the fingerprint merge, so we feed it
    # the assets table we have already pulled. Submitting the two in
    # parallel still works because we re-issue the visual_assets call
    # with ``asset_map`` once the assets future resolves; that cost
    # is negligible because the row is already in sqlite's page cache.
    future_assets = pool.submit(store.list_assets, limit=None)
    future_systems = pool.submit(store.list_visual_systems, limit=None)
    future_recipes = pool.submit(store.list_recipes, limit=None)
    future_generations = pool.submit(store.list_generation_runs, limit=None)
    future_favorites = pool.submit(store.list_panel_favorites)
    future_system_relations = pool.submit(store.list_visual_system_assets)
    future_recipe_relations = pool.submit(store.list_recipe_assets)
    assets = future_assets.result()
    asset_map = {asset["id"]: asset for asset in assets}
    visual_assets = store.list_visual_assets(limit=None, asset_map=asset_map)
    systems = future_systems.result()
    recipes = future_recipes.result()
    generations = future_generations.result()
    favorite_rows = future_favorites.result()
    system_relations = future_system_relations.result()
    recipe_relations = future_recipe_relations.result()
    asset_map = {asset["id"]: asset for asset in assets}
    path_to_asset_id = {asset["asset_path"]: asset["id"] for asset in assets}
    system_assets_by_system_id: dict[str, list[dict[str, Any]]] = {}
    for relation in system_relations:
        system_assets_by_system_id.setdefault(relation["system_id"], []).append(relation)
    recipe_assets_by_recipe_id: dict[str, list[dict[str, Any]]] = {}
    for relation in recipe_relations:
        recipe_assets_by_recipe_id.setdefault(relation["recipe_id"], []).append(relation)
    (
        generated_by_visual_asset,
        visual_asset_by_id,
    ) = _generated_outputs_by_visual_asset(visual_assets, generations)
    tables = {
        "asset_map": asset_map,
        "path_to_asset_id": path_to_asset_id,
        "visual_assets": visual_assets,
        "visual_asset_by_id": visual_asset_by_id,
        "systems": systems,
        "system_by_id": {system["id"]: system for system in systems},
        "recipes": recipes,
        "recipe_by_id": {recipe["id"]: recipe for recipe in recipes},
        "generations": generations,
        "favorite_rows": favorite_rows,
        "favorite_keys": {(row["entity_type"], row["entity_id"]) for row in favorite_rows},
        "favorite_created_at": {
            (row["entity_type"], row["entity_id"]): row["created_at"]
            for row in favorite_rows
        },
        "system_assets_by_system_id": system_assets_by_system_id,
        "recipe_assets_by_recipe_id": recipe_assets_by_recipe_id,
        "generated_by_visual_asset": generated_by_visual_asset,
    }
    _panel_lookup_cache = tables
    _panel_lookup_expires_at = time.monotonic() + _LOOKUP_TTL_SECONDS
    _panel_lookup_filled.set()
    return tables


def _gather_lookup_tables(store: AetherStore) -> dict[str, Any]:
    """Fetch every panel read table in a single pass and pre-group joins.

    Each section collector (``visual_assets`` / ``visual_systems`` /
    ``recipes`` / ``favorites``) needs the same handful of full tables
    to resolve ids into rows. Doing those scans per-collector used to
    add 2-3 round trips *per request* on top of the per-entity
    ``list_recipe_assets`` / ``list_visual_system_assets`` calls, and
    the per-entity calls were themselves an N+1 (one query per
    system / recipe). This helper runs the full scans **once** and
    groups the join tables (``visual_system_assets`` /
    ``recipe_assets``) by their parent id so the per-entity builders
    can iterate in memory instead of issuing a SQL query per row.

    The result is memoised for ``_LOOKUP_TTL_SECONDS`` so a parallel
    batch of section requests triggered by the page open only pays the
    full-table cost once. Concurrent callers triggered by a single
    page open also collapse onto the same fill (via the
    ``_panel_lookup_filled`` event) so we do not serialise N
    independent cold walks behind the cache lock.
    """
    global _panel_lookup_cache, _panel_lookup_expires_at
    now = time.monotonic()
    cached = _panel_lookup_cache
    if cached is not None and now < _panel_lookup_expires_at:
        return cached
    if _panel_lookup_filled.is_set() and cached is not None and now < _panel_lookup_expires_at:
        return cached
    with _panel_lookup_lock:
        cached = _panel_lookup_cache
        if cached is not None and now < _panel_lookup_expires_at:
            return cached
        # Reset the event *before* walking so concurrent waiters see
        # the new fill. The previous fill is still cached until the
        # new one overwrites it, so they can return the old snapshot
        # if they really cannot wait.
        _panel_lookup_filled.clear()
        return _fill_lookup_tables(store)


def _load_panel_lookup_tables(store: AetherStore) -> dict[str, Any]:
    """Backwards-compatible subset of :func:`_gather_lookup_tables`.

    Older callers (and tests) only need the ``asset_map`` /
    ``system_by_id`` / ``visual_asset_by_id`` /
    ``generated_by_visual_asset`` keys, so we project the shared cache
    down to that shape. The cost is still a single pass through
    :func:`_gather_lookup_tables`.
    """
    tables = _gather_lookup_tables(store)
    return {
        "asset_map": tables["asset_map"],
        "system_by_id": tables["system_by_id"],
        "visual_asset_by_id": tables["visual_asset_by_id"],
        "generated_by_visual_asset": tables["generated_by_visual_asset"],
    }


def _related_assets_from_relations(
    relations: list[dict[str, Any]],
    visual_asset_by_id: dict[str, dict[str, Any]],
    generated_by_visual_asset: dict[str, list[str]],
    asset_map: dict[str, dict[str, Any]],
    *,
    kind: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the ``related_assets`` and ``related_generated_images`` arrays for one entity.

    Returns ``(related_assets, related_generated_images)`` where each
    element is shaped the way the panel renderer expects.
    ``kind`` is ``"visual_system"`` or ``"recipe"`` and is reserved
    for any future per-kind divergence; both shapes are identical today.
    """
    del kind  # placeholder for future per-kind divergence
    related_assets = [
        {
            "id": relation["asset_id"],
            "role": relation.get("role", "optional"),
            "weight": relation.get("weight", 0),
            "reason": relation.get("reason", ""),
            "name": visual_asset_by_id.get(relation["asset_id"], {}).get("name", relation["asset_id"]),
            "type": visual_asset_by_id.get(relation["asset_id"], {}).get("type", ""),
            "summary": visual_asset_by_id.get(relation["asset_id"], {}).get("summary", ""),
            "status": visual_asset_by_id.get(relation["asset_id"], {}).get("status", ""),
        }
        for relation in relations
    ]
    related_generated_ids: list[str] = []
    for relation in relations:
        related_generated_ids.extend(generated_by_visual_asset.get(relation["asset_id"], []))
    related_generated_images = _resolve_images(related_generated_ids, asset_map, kind="generated")
    return related_assets, related_generated_images


def _build_visual_system_item(
    system: dict[str, Any],
    *,
    asset_map: dict[str, dict[str, Any]],
    visual_asset_by_id: dict[str, dict[str, Any]],
    generated_by_visual_asset: dict[str, list[str]],
    system_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the panel item dict for a single visual system.

    Lookups (``asset_map`` / ``visual_asset_by_id`` /
    ``generated_by_visual_asset``) must be pre-loaded by the caller via
    :func:`_load_panel_lookup_tables` so the cost is amortised across
    every system in the list. ``system_assets`` is the per-system
    join row set returned by ``store.list_visual_system_assets``.
    """
    reference_ids = [
        asset_id
        for asset_id in system.get("source_reference_ids", [])
        if isinstance(asset_id, str)
    ]
    direct_images = _resolve_images(reference_ids, asset_map)
    direct_reference_images = [image for image in direct_images if image["kind"] == "reference"]
    direct_generated_images = [image for image in direct_images if image["kind"] == "generated"]
    related_assets, related_generated_images = _related_assets_from_relations(
        system_assets,
        visual_asset_by_id,
        generated_by_visual_asset,
        asset_map,
        kind="visual_system",
    )
    return {
        "id": system["id"],
        "kind": system["kind"],
        "name": system["name"],
        "summary": _compact_text(system.get("summary", "")),
        "definition": system.get("summary", ""),
        "tags": system.get("tags", []),
        "visual_rules": system.get("visual_rules", []),
        "avoid_rules": system.get("avoid_rules", []),
        "status": system["status"],
        "updated_at": system["updated_at"],
        "entity_type": "visual_system",
        "source_view": "visual_systems",
        "is_favorite": False,
        "favorite_at": None,
        "related_assets": related_assets,
        "reference_images": direct_reference_images,
        "generated_images": _merge_images(direct_generated_images, related_generated_images),
    }


def _build_recipe_item(
    recipe: dict[str, Any],
    *,
    asset_map: dict[str, dict[str, Any]],
    system_by_id: dict[str, dict[str, Any]],
    visual_asset_by_id: dict[str, dict[str, Any]],
    generated_by_visual_asset: dict[str, list[str]],
    recipe_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the panel item dict for a single recipe.

    Lookups (``asset_map`` / ``system_by_id`` / ``visual_asset_by_id`` /
    ``generated_by_visual_asset``) must be pre-loaded by the caller via
    :func:`_load_panel_lookup_tables`. ``recipe_assets`` is the
    per-recipe join row set returned by ``store.list_recipe_assets``.
    """
    reference_ids = [
        asset_id
        for asset_id in recipe.get("source_reference_ids", [])
        if isinstance(asset_id, str)
    ]
    direct_images = _resolve_images(reference_ids, asset_map)
    direct_reference_images = [image for image in direct_images if image["kind"] == "reference"]
    direct_generated_images = [image for image in direct_images if image["kind"] == "generated"]
    related_assets, related_generated_images = _related_assets_from_relations(
        recipe_assets,
        visual_asset_by_id,
        generated_by_visual_asset,
        asset_map,
        kind="recipe",
    )
    parent_systems = [
        {
            "id": system_id,
            "name": system_by_id.get(system_id, {}).get("name", system_id),
            "kind": system_by_id.get(system_id, {}).get("kind", ""),
            "status": system_by_id.get(system_id, {}).get("status", ""),
        }
        for system_id in recipe.get("parent_system_ids", [])
        if isinstance(system_id, str)
    ]
    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "summary": _compact_text(recipe.get("summary", "")),
        "definition": recipe.get("summary", ""),
        "status": recipe["status"],
        "source": recipe.get("source", ""),
        "reason": recipe.get("reason", ""),
        "updated_at": recipe["updated_at"],
        "entity_type": "recipe",
        "source_view": "recipes",
        "is_favorite": False,
        "favorite_at": None,
        "parent_systems": parent_systems,
        "use_cases": recipe.get("use_cases", []),
        "required_asset_types": recipe.get("required_asset_types", []),
        "composition_rules": recipe.get("composition_rules", []),
        "recommended_aspect_ratios": recipe.get("recommended_aspect_ratios", []),
        "confidence": recipe.get("confidence"),
        "related_assets": related_assets,
        "reference_images": direct_reference_images,
        "generated_images": _merge_images(direct_generated_images, related_generated_images),
    }


def collect_panel_visual_systems(
    config: LoadedConfig, store: AetherStore
) -> list[dict[str, Any]]:
    """Return just the visual system items from :func:`collect_panel_data`.

    Uses the shared lookup cache from :func:`_gather_lookup_tables` so
    the per-system ``list_visual_system_assets`` join runs once for
    the whole table (and is grouped in Python) rather than once per
    system.
    """
    lookups = _gather_lookup_tables(store)
    system_assets_by_system_id = lookups["system_assets_by_system_id"]
    return [
        _build_visual_system_item(
            system,
            asset_map=lookups["asset_map"],
            visual_asset_by_id=lookups["visual_asset_by_id"],
            generated_by_visual_asset=lookups["generated_by_visual_asset"],
            system_assets=system_assets_by_system_id.get(system["id"], []),
        )
        for system in lookups["systems"]
    ]


def collect_panel_recipes(config: LoadedConfig, store: AetherStore) -> list[dict[str, Any]]:
    """Return just the recipe items from :func:`collect_panel_data`.

    Uses the shared lookup cache from :func:`_gather_lookup_tables` so
    the per-recipe ``list_recipe_assets`` join runs once for the
    whole table (and is grouped in Python) rather than once per
    recipe.
    """
    lookups = _gather_lookup_tables(store)
    recipe_assets_by_recipe_id = lookups["recipe_assets_by_recipe_id"]
    return [
        _build_recipe_item(
            recipe,
            asset_map=lookups["asset_map"],
            system_by_id=lookups["system_by_id"],
            visual_asset_by_id=lookups["visual_asset_by_id"],
            generated_by_visual_asset=lookups["generated_by_visual_asset"],
            recipe_assets=recipe_assets_by_recipe_id.get(recipe["id"], []),
        )
        for recipe in lookups["recipes"]
    ]


def collect_panel_favorites(config: LoadedConfig, store: AetherStore) -> list[dict[str, Any]]:
    """Return the panel ``favorites`` block from :func:`collect_panel_data`.

    Each favorite row is just ``(entity_type, entity_id)``. The
    renderer needs the full item shape (with ``reference_images`` /
    ``generated_images`` / ``related_assets`` / ``parent_systems``),
    so we share the per-entity item builders with the section
    collectors. The expensive asset / system / visual_asset /
    generation walks happen once via :func:`_gather_lookup_tables`,
    and the per-entity join rows are looked up in the pre-grouped
    ``system_assets_by_system_id`` / ``recipe_assets_by_recipe_id``
    tables.
    """
    favorite_rows = store.list_panel_favorites()
    if not favorite_rows:
        return []
    lookups = _gather_lookup_tables(store)
    asset_map = lookups["asset_map"]
    system_by_id = lookups["system_by_id"]
    visual_asset_by_id = lookups["visual_asset_by_id"]
    generated_by_visual_asset = lookups["generated_by_visual_asset"]
    recipe_by_id = lookups["recipe_by_id"]
    system_assets_by_system_id = lookups["system_assets_by_system_id"]
    recipe_assets_by_recipe_id = lookups["recipe_assets_by_recipe_id"]
    favorites: list[dict[str, Any]] = []
    for row in favorite_rows:
        entity_type = row["entity_type"]
        entity_id = row["entity_id"]
        if entity_type == "recipe":
            recipe = recipe_by_id.get(entity_id)
            if recipe is None:
                continue
            item = _build_recipe_item(
                recipe,
                asset_map=asset_map,
                system_by_id=system_by_id,
                visual_asset_by_id=visual_asset_by_id,
                generated_by_visual_asset=generated_by_visual_asset,
                recipe_assets=recipe_assets_by_recipe_id.get(entity_id, []),
            )
        elif entity_type == "visual_system":
            system = system_by_id.get(entity_id)
            if system is None:
                continue
            item = _build_visual_system_item(
                system,
                asset_map=asset_map,
                visual_asset_by_id=visual_asset_by_id,
                generated_by_visual_asset=generated_by_visual_asset,
                system_assets=system_assets_by_system_id.get(entity_id, []),
            )
        else:
            continue
        item["is_favorite"] = True
        item["favorite_at"] = row["created_at"]
        favorites.append(item)
    favorites.sort(
        key=lambda item: item.get("favorite_at") or item.get("updated_at") or "",
        reverse=True,
    )
    return favorites
