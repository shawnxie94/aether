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
