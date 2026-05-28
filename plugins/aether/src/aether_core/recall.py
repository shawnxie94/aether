from __future__ import annotations

import re
from typing import Any


def token_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        value = " ".join(str(item) for pair in value.items() for item in pair)
    elif isinstance(value, list):
        value = " ".join(str(item) for item in value)
    else:
        value = str(value)
    return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower()) if len(token) >= 2}


def lexical_similarity(left: Any, right: Any) -> tuple[float, list[str]]:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0, []
    matched = sorted(left_tokens & right_tokens)
    score = len(matched) / len(left_tokens | right_tokens)
    return score, matched[:12]


def flatten_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        texts: list[str] = []
        for key, item in value.items():
            texts.append(str(key))
            texts.extend(flatten_text(item))
        return texts
    if isinstance(value, list):
        return [text for item in value for text in flatten_text(item)]
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    return []


def canonical_text(parts: list[Any]) -> str:
    texts = [text for part in parts for text in flatten_text(part) if text]
    seen: set[str] = set()
    unique = []
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return "\n".join(unique)


def weighted_score(
    semantic_score: float,
    lexical_score: float,
    relation_score: float = 0.0,
    quality_score: float = 0.0,
) -> float:
    return round(
        0.55 * semantic_score
        + 0.25 * lexical_score
        + 0.15 * relation_score
        + 0.05 * quality_score,
        4,
    )
