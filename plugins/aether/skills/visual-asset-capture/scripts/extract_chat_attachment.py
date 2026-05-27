#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.assets import ingest_asset
from aether_core.config import ensure_configured_dirs, load_config
from aether_core.storage import AetherStore


DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.*)$")


def safe_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return name or "chat-attachment"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def latest_session_path() -> Path:
    sessions_root = codex_home() / "sessions"
    candidates = list(sessions_root.glob("**/rollout-*.jsonl"))
    if not candidates:
        raise SystemExit(f"No Codex session JSONL files found under {sessions_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def iter_input_images(session_path: Path):
    with session_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if "input_image" not in line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload", {})
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            for part_index, part in enumerate(payload.get("content", [])):
                if not isinstance(part, dict):
                    continue
                image_url = part.get("image_url", "")
                if part.get("type") == "input_image" and image_url.startswith("data:image/"):
                    yield {
                        "line_number": line_number,
                        "part_index": part_index,
                        "image_url": image_url,
                    }


def decode_data_url(image_url: str) -> tuple[str, bytes]:
    match = DATA_URL_RE.match(image_url)
    if not match:
        raise SystemExit("Only base64 data:image URLs are supported")
    try:
        data = base64.b64decode(match.group("data"), validate=True)
    except ValueError as exc:
        raise SystemExit(f"Invalid base64 image data: {exc}") from exc
    return match.group("mime"), data


def find_existing_asset(config: Any, sha256: str, kind: str) -> dict[str, Any] | None:
    with sqlite3.connect(config.database_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "select * from assets where sha256 = ? and kind = ? order by created_at asc limit 1",
            (sha256, kind),
        ).fetchone()
    return dict(row) if row else None


def build_source_reference(args: argparse.Namespace, asset: dict[str, Any], mime_type: str) -> dict[str, Any]:
    reference = {
        "image_path": asset["asset_path"],
        "original_image_path": f"chat_attachment:{args.reference_name}",
        "role": args.role,
        "asset_id": asset["id"],
        "sha256": asset["sha256"],
        "mime_type": asset.get("mime_type", mime_type),
        "size_bytes": asset.get("size_bytes", 0),
        "user_note": args.user_note
        or "Reference image was uploaded as a Codex chat attachment, extracted from the session input_image data URL, and ingested into Aether reference asset storage.",
    }
    if args.source_prompt:
        reference["source_prompt"] = args.source_prompt
    return reference


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract a Codex chat attachment data URL from a session JSONL and ingest it as an Aether reference asset."
    )
    parser.add_argument("--session", help="Codex rollout JSONL path. Defaults to the newest session under $CODEX_HOME/sessions.")
    parser.add_argument("--index", type=int, default=0, help="Zero-based input_image index across user messages in the session.")
    parser.add_argument("--reference-name", required=True, help="Stable name used for the decoded cache file and chat reference.")
    parser.add_argument("--role", default="positive_reference")
    parser.add_argument("--source-prompt")
    parser.add_argument("--user-note")
    parser.add_argument("--kind", choices=["reference", "generated"], default="reference")
    args = parser.parse_args()

    session_path = Path(args.session).expanduser().resolve() if args.session else latest_session_path()
    images = list(iter_input_images(session_path))
    if args.index < 0 or args.index >= len(images):
        raise SystemExit(f"input_image index {args.index} out of range; found {len(images)} image(s)")

    selected = images[args.index]
    mime_type, image_bytes = decode_data_url(selected["image_url"])
    extension = mimetypes.guess_extension(mime_type) or ".png"
    if extension == ".jpe":
        extension = ".jpg"

    config = load_config()
    ensure_configured_dirs(config)
    cache_dir = config.resolve_path(config.data["storage"]["cacheDir"]) / "chat-attachments"
    cache_dir.mkdir(parents=True, exist_ok=True)
    decoded_path = cache_dir / f"{safe_name(args.reference_name)}{extension}"
    decoded_path.write_bytes(image_bytes)

    store = AetherStore(config.database_path)
    store.init()
    asset_payload = ingest_asset(config, decoded_path, args.kind)
    asset = find_existing_asset(config, asset_payload["sha256"], args.kind) or store.create_asset(asset_payload)
    source_reference = build_source_reference(args, asset, mime_type)

    result: dict[str, Any] = {
        "session_path": str(session_path),
        "input_image_index": args.index,
        "input_image_line_number": selected["line_number"],
        "decoded_path": str(decoded_path),
        "asset": asset,
        "source_reference": source_reference,
    }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
