from __future__ import annotations

import re
import uuid


def slugify(value: str, prefix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = uuid.uuid4().hex[:12]
    return f"{prefix}_{slug}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

