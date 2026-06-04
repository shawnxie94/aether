from __future__ import annotations

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
        "size_bytes": asset.get("size_bytes", 0),
        "exists": path.exists(),
    }


def _compact_text(value: str, limit: int = 180) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "..."


def _resolve_images(asset_ids: list[str], asset_map: dict[str, dict[str, Any]], kind: str | None = None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    images: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        asset = asset_map.get(asset_id)
        if not asset:
            continue
        if kind and asset.get("kind") != kind:
            continue
        images.append(_image_from_asset(asset))
    return images


def _merge_images(*image_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    images: list[dict[str, Any]] = []
    for group in image_groups:
        for image in group:
            image_id = image.get("id")
            if not image_id or image_id in seen:
                continue
            seen.add(image_id)
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
