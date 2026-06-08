from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from .assets import ingest_asset
from .storage import AetherStore


DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.*)$")


def safe_chat_attachment_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return name or "chat-attachment"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def latest_session_path() -> Path:
    sessions_root = codex_home() / "sessions"
    candidates = list(sessions_root.glob("**/rollout-*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No Codex session JSONL files found under {sessions_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _decode_data_url(image_url: str) -> tuple[str, bytes]:
    match = DATA_URL_RE.match(image_url)
    if not match:
        raise ValueError("Only base64 data:image URLs are supported")
    return match.group("mime"), base64.b64decode(match.group("data"), validate=True)


def iter_user_image_messages(session_path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
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
            images: list[dict[str, Any]] = []
            texts: list[str] = []
            for part_index, part in enumerate(payload.get("content", [])):
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "input_text":
                    texts.append(str(part.get("text", "")))
                image_url = part.get("image_url", "")
                if part.get("type") == "input_image" and image_url.startswith("data:image/"):
                    images.append(
                        {
                            "line_number": line_number,
                            "part_index": part_index,
                            "image_url": image_url,
                        }
                    )
            if images:
                messages.append({"line_number": line_number, "text": "\n".join(texts), "images": images})
    return messages


def find_recent_input_images(count: int, session_path: Path | None = None) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    resolved_session = session_path or latest_session_path()
    messages = iter_user_image_messages(resolved_session)
    for message in reversed(messages):
        if len(message["images"]) >= count:
            return message["images"][:count]
    raise ValueError(f"Could not find a user message with at least {count} input_image attachment(s)")


def find_input_images_by_indices(indices: list[int], session_path: Path | None = None) -> list[dict[str, Any]]:
    resolved_session = session_path or latest_session_path()
    images = [image for message in iter_user_image_messages(resolved_session) for image in message["images"]]
    selected: list[dict[str, Any]] = []
    for index in indices:
        if index < 0 or index >= len(images):
            raise ValueError(f"input_image index {index} out of range; found {len(images)} image(s)")
        selected.append(images[index])
    return selected


def ingest_chat_attachment(
    config: Any,
    store: AetherStore,
    image_url: str,
    reference_name: str,
    kind: str = "reference",
) -> dict[str, Any]:
    mime_type, image_bytes = _decode_data_url(image_url)
    extension = mimetypes.guess_extension(mime_type) or ".png"
    if extension == ".jpe":
        extension = ".jpg"
    storage = config.data.get("storage", {})
    cache_dir = config.resolve_path(storage.get("cacheDir", "cache")) / "chat-attachments"
    cache_dir.mkdir(parents=True, exist_ok=True)
    decoded_path = cache_dir / f"{safe_chat_attachment_name(reference_name)}{extension}"
    decoded_path.write_bytes(image_bytes)

    sha256 = hashlib.sha256(image_bytes).hexdigest()
    existing = store.find_asset_by_sha256(sha256, kind)
    asset = existing or store.create_asset(ingest_asset(config, decoded_path, kind))
    return {
        "asset": asset,
        "decoded_path": str(decoded_path),
        "mime_type": mime_type,
    }


def is_unresolved_chat_reference(reference: Any) -> bool:
    return (
        isinstance(reference, dict)
        and str(reference.get("original_image_path", "")).startswith("chat_attachment:")
        and not reference.get("image_path")
        and not reference.get("asset_id")
    )


def chat_reference_name(reference: dict[str, Any], fallback_index: int) -> str:
    original = str(reference.get("original_image_path", ""))
    if original.startswith("chat_attachment:"):
        return original.split(":", 1)[1] or f"chat-attachment-{fallback_index}"
    return f"chat-attachment-{fallback_index}"
