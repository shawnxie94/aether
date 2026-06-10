from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from .config import LoadedConfig
from .image_fingerprint import (
    compute_fingerprint,
    is_pillow_available,
    load_cached_fingerprint,
    write_cached_fingerprint,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_dir_for_kind(config: LoadedConfig, kind: str) -> Path:
    storage = config.data["storage"]
    if kind == "reference":
        return config.resolve_path(storage["referenceImageDir"])
    if kind == "generated":
        return config.resolve_path(storage["generatedImageDir"])
    return config.resolve_path(storage["assetRoot"]) / kind


def _should_fingerprint(config: LoadedConfig, kind: str, mime_type: str | None) -> bool:
    """Skip fingerprint work for non-image assets or when explicitly disabled.

    Operators can opt out by setting ``storage.fingerprint.enabled = false``
    in the aether config, and the path also rejects anything that does not
    look like an image MIME type so we never load non-PNG/JPEG binaries
    into Pillow.
    """

    if not is_pillow_available():
        return False
    storage = (config.data.get("storage") or {}) if hasattr(config, "data") else {}
    fingerprint_cfg = storage.get("fingerprint") or {}
    if isinstance(fingerprint_cfg, dict) and fingerprint_cfg.get("enabled") is False:
        return False
    if not mime_type or not mime_type.startswith("image/"):
        return False
    # ``generated`` images flow through the same path; the cost is bounded
    # because the destination is already on disk and the work is cached.
    return True


def _fingerprint_for(config: LoadedConfig, asset_path: str) -> dict[str, Any]:
    """Return a cached fingerprint when present, else compute and cache it.

    The sidecar file lives next to the asset so re-ingest (e.g. when
    re-importing a chat attachment that resolves to the same digest) is
    effectively free.
    """

    cached = load_cached_fingerprint(asset_path)
    if cached is not None:
        return cached
    include_clip = bool(((config.data.get("storage") or {}).get("fingerprint") or {}).get("clip", True))
    fingerprint = compute_fingerprint(asset_path, include_clip=include_clip)
    if fingerprint:
        write_cached_fingerprint(asset_path, fingerprint)
    return fingerprint


def ingest_asset(config: LoadedConfig, source: str | Path, kind: str) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Asset not found: {source_path}")
    if not source_path.is_file():
        raise ValueError(f"Asset is not a file: {source_path}")

    digest = sha256_file(source_path)
    destination_dir = asset_dir_for_kind(config, kind)
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower()
    destination = destination_dir / f"{digest[:16]}{suffix}"
    if not destination.exists():
        shutil.copy2(source_path, destination)

    mime_type, _ = mimetypes.guess_type(destination.name)
    mime_type = mime_type or "application/octet-stream"

    record: dict[str, Any] = {
        "kind": kind,
        "source_path": str(source_path),
        "asset_path": str(destination),
        "sha256": digest,
        "mime_type": mime_type,
        "size_bytes": destination.stat().st_size,
    }
    if _should_fingerprint(config, kind, mime_type):
        try:
            fingerprint = _fingerprint_for(config, str(destination))
        except Exception:
            fingerprint = {}
        if fingerprint:
            record["fingerprint"] = fingerprint
    return record
