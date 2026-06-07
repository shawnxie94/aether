from __future__ import annotations

import hashlib

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
    path = Path(asset.get("asset_path", ""))
    return {
        "id": asset["id"],
        "kind": asset["kind"],
        "src": f"/asset/{asset['id']}",
        "label": path.name or asset["id"],
        "sha256": asset.get("sha256", ""),
        "size_bytes": asset.get("size_bytes", 0),
        "exists": path.exists(),
    }


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
    """
    visual_assets = store.list_visual_assets(limit=None)
    systems = store.list_visual_systems(limit=None)
    recipes = store.list_recipes(limit=None)
    generations = store.list_generation_runs(limit=None)
    favorite_rows = store.list_panel_favorites()
    assets = store.list_assets(limit=None)
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
    """Return just the visual asset items from :func:`collect_panel_data`."""
    assets = store.list_assets(limit=None)
    asset_map = {asset["id"]: asset for asset in assets}
    path_to_asset_id = {asset["asset_path"]: asset["id"] for asset in assets}
    visual_assets = store.list_visual_assets(limit=None)
    generations = store.list_generation_runs(limit=None)
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
            }
        )
    return items


def collect_panel_visual_systems(
    config: LoadedConfig, store: AetherStore
) -> list[dict[str, Any]]:
    """Return just the visual system items from :func:`collect_panel_data`."""
    assets = store.list_assets(limit=None)
    asset_map = {asset["id"]: asset for asset in assets}
    systems = store.list_visual_systems(limit=None)
    visual_assets = store.list_visual_assets(limit=None)
    generations = store.list_generation_runs(limit=None)
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
    items: list[dict[str, Any]] = []
    for system in systems:
        reference_ids = [
            asset_id
            for asset_id in system.get("source_reference_ids", [])
            if isinstance(asset_id, str)
        ]
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
        items.append(
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
                "is_favorite": False,
                "favorite_at": None,
                "related_assets": related_assets,
                "reference_images": direct_reference_images,
                "generated_images": _merge_images(direct_generated_images, related_generated_images),
            }
        )
    return items


def collect_panel_recipes(config: LoadedConfig, store: AetherStore) -> list[dict[str, Any]]:
    """Return just the recipe items from :func:`collect_panel_data`."""
    assets = store.list_assets(limit=None)
    asset_map = {asset["id"]: asset for asset in assets}
    systems = store.list_visual_systems(limit=None)
    system_by_id = {system["id"]: system for system in systems}
    visual_assets = store.list_visual_assets(limit=None)
    visual_asset_by_id = {asset["id"]: asset for asset in visual_assets}
    recipes = store.list_recipes(limit=None)
    generations = store.list_generation_runs(limit=None)
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
    items: list[dict[str, Any]] = []
    for recipe in recipes:
        reference_ids = [
            asset_id
            for asset_id in recipe.get("source_reference_ids", [])
            if isinstance(asset_id, str)
        ]
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
        related_generated_ids: list[str] = []
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
        items.append(
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
        )
    return items


def collect_panel_favorites(config: LoadedConfig, store: AetherStore) -> list[dict[str, Any]]:
    """Return the panel ``favorites`` block from :func:`collect_panel_data`.

    The favorite row only carries the entity id, so we re-run the
    system and recipe collectors to get the fully-shaped panel item
    (with ``reference_images`` / ``generated_images`` /
    ``related_assets`` / ``parent_systems`` / ...). Without that
    enrichment the list and detail renderers fall back to ``No
    linked image`` placeholders, which is a regression from the
    legacy full-payload endpoint.
    """
    favorite_rows = store.list_panel_favorites()
    favorite_at = {
        (row["entity_type"], row["entity_id"]): row["created_at"]
        for row in favorite_rows
    }
    candidate_items: list[dict[str, Any]] = [
        *collect_panel_recipes(config, store),
        *collect_panel_visual_systems(config, store),
    ]
    favorites: list[dict[str, Any]] = []
    for item in candidate_items:
        key = (item.get("entity_type"), item.get("id"))
        if key not in favorite_at:
            continue
        item["is_favorite"] = True
        item["favorite_at"] = favorite_at[key]
        # The per-section collectors tag items with their owning tab so
        # the detail view can re-locate them. Favorites lives on its
        # own tab, so we keep ``source_view`` for the in-tab Back
        # navigation to land on the originating list.
        favorites.append(item)
    favorites.sort(
        key=lambda item: item.get("favorite_at") or item.get("updated_at") or "",
        reverse=True,
    )
    return favorites
