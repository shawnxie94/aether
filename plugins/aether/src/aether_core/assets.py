from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from .config import LoadedConfig


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
    return {
        "kind": kind,
        "source_path": str(source_path),
        "asset_path": str(destination),
        "sha256": digest,
        "mime_type": mime_type or "application/octet-stream",
        "size_bytes": destination.stat().st_size,
    }

