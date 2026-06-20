from __future__ import annotations

import base64
import mimetypes
import re
import urllib.request
from pathlib import Path
from typing import Any

from .assets import ingest_asset
from .ids import new_id


DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[-+.\w]+);base64,(?P<data>.+)$", re.DOTALL)


def _cache_output_path(config: Any, suffix: str) -> Path:
    cache_dir = config.resolve_path(config.data["storage"]["cacheDir"]) / "generated-outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{new_id('generated')}{suffix}"


def _path_from_local_reference(config: Any, value: str) -> Path:
    path = Path(value).expanduser()
    if path.exists():
        return path.resolve()
    if not path.is_absolute():
        resolved = config.resolve_path(path)
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"Generated output file not found: {value}")


def _path_from_data_url(config: Any, value: str) -> Path:
    match = DATA_URL_RE.match(value)
    if not match:
        raise ValueError("Unsupported data URL output. Expected data:image/*;base64,...")
    mime_type = match.group("mime")
    suffix = mimetypes.guess_extension(mime_type) or ".img"
    path = _cache_output_path(config, suffix)
    path.write_bytes(base64.b64decode(match.group("data")))
    return path


def _path_from_url(config: Any, value: str) -> Path:
    request = urllib.request.Request(value, headers={"User-Agent": "Aether/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        suffix = mimetypes.guess_extension(content_type) or Path(value).suffix or ".img"
        path = _cache_output_path(config, suffix)
        path.write_bytes(response.read())
        return path


def _source_from_output(output: Any) -> tuple[str, Any]:
    if isinstance(output, str):
        return "value", output
    if isinstance(output, dict):
        for key in ("asset_path", "image_path", "file_path", "path", "url"):
            value = output.get(key)
            if isinstance(value, str) and value:
                return key, value
    raise ValueError(f"Unsupported generated output shape: {output!r}")


def _source_to_path(config: Any, value: str) -> Path:
    if value.startswith("data:image/"):
        return _path_from_data_url(config, value)
    if value.startswith(("http://", "https://")):
        return _path_from_url(config, value)
    return _path_from_local_reference(config, value)


def archive_output(config: Any, store: Any, output: Any) -> dict[str, Any]:
    source_key, source_value = _source_from_output(output)
    source_path = _source_to_path(config, source_value)
    asset = store.create_asset(ingest_asset(config, source_path, "generated"))
    archived = {
        "asset_id": asset["id"],
        "asset_path": asset["asset_path"],
        "image_path": asset["asset_path"],
        "sha256": asset["sha256"],
        "mime_type": asset["mime_type"],
        "size_bytes": asset["size_bytes"],
        "original_output": source_value,
        "original_output_key": source_key,
    }
    if isinstance(output, dict):
        archived = {**output, **archived}
    return archived


def archive_generation_outputs(config: Any, store: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") not in {"generated", "edited"}:
        return payload

    outputs = payload.get("outputs") or []
    if not outputs:
        raise ValueError("Generated or edited runs must include at least one output image to archive.")

    payload["outputs"] = [archive_output(config, store, output) for output in outputs]
    return payload


def _normalize_selected_assets(existing: Any) -> list[str]:
    """Coerce a ``selected_assets`` payload into a deduplicated list of ids.

    Accepts the same shapes the panel lookup already tolerates — bare id
    strings, ``{"asset_id": "..."}`` dicts, or ``{"id": "..."}`` dicts.
    Unknown shapes are dropped silently so this function is safe to call
    on partial / older payloads.
    """
    if not isinstance(existing, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for item in existing:
        if isinstance(item, str):
            candidate = item
        elif isinstance(item, dict):
            candidate = item.get("asset_id") or item.get("id") or ""
        else:
            candidate = ""
        if isinstance(candidate, str) and candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _relation_asset_ids(store: Any, *, recipe_id: str | None, visual_system_id: str | None) -> list[str]:
    """Resolve visual asset ids linked to a Recipe or Visual System.

    Pulls the per-relation join rows so we capture every linked asset
    (core + optional) without forcing the caller to know the schema.
    Missing / inactive entities contribute no ids and never raise.
    """
    ids: list[str] = []
    if recipe_id:
        recipe = store.get_recipe(recipe_id, include_assets=False)
        if recipe and recipe.get("status") != "archived":
            for relation in store.list_recipe_assets(recipe_id=recipe_id):
                asset_id = relation.get("asset_id")
                if isinstance(asset_id, str) and asset_id:
                    ids.append(asset_id)
    if visual_system_id:
        system = store.get_visual_system(visual_system_id, include_assets=False)
        if system and system.get("status") != "archived":
            for relation in store.list_visual_system_assets(system_id=visual_system_id):
                asset_id = relation.get("asset_id")
                if isinstance(asset_id, str) and asset_id:
                    ids.append(asset_id)
    return ids


def resolve_generation_relations(payload: dict[str, Any], store: Any) -> dict[str, Any]:
    """Inject referenced visual assets into ``selected_assets``.

    The Aether storage layer wires panels and reuse suggestions through
    ``generation_runs.selected_assets`` (it is the only signal used by
    ``_generated_outputs_by_visual_asset`` and ``_record_generation_evidence``).
    Callers that only know a Recipe / Visual System / subject id used to
    lose the linkage because no helper bridged those references into
    ``selected_assets``. This function fills that gap in place:

    - Keeps any ids the caller already wrote.
    - Appends the Recipe's linked assets when ``recipe_id`` is set.
    - Appends the Visual System's linked assets when
      ``visual_system_id`` is set.
    - Appends the explicit ``subject_asset_id`` last so it stays
      discoverable even when no Recipe or Visual System is referenced.
    - De-duplicates while preserving the first occurrence order.

    The function is a no-op for payloads that already carry a non-empty
    ``selected_assets`` *and* no Recipe / Visual System / subject
    reference, so existing scripts that pass a fully-resolved list keep
    their exact ordering.
    """
    if not isinstance(payload, dict):
        return payload

    referenced_ids: list[str] = []
    recipe_id = payload.get("recipe_id")
    if isinstance(recipe_id, str) and recipe_id:
        referenced_ids.extend(_relation_asset_ids(store, recipe_id=recipe_id, visual_system_id=None))
    visual_system_id = payload.get("visual_system_id")
    if isinstance(visual_system_id, str) and visual_system_id:
        referenced_ids.extend(_relation_asset_ids(store, recipe_id=None, visual_system_id=visual_system_id))
    subject_asset_id = payload.get("subject_asset_id")
    if isinstance(subject_asset_id, str) and subject_asset_id:
        referenced_ids.append(subject_asset_id)

    if not referenced_ids:
        return payload

    existing = _normalize_selected_assets(payload.get("selected_assets"))
    if not existing and not referenced_ids:
        return payload

    seen: set[str] = set(existing)
    merged: list[str] = list(existing)
    for asset_id in referenced_ids:
        if asset_id not in seen:
            seen.add(asset_id)
            merged.append(asset_id)

    payload["selected_assets"] = merged
    return payload
