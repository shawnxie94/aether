from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


FIELD_MAP = {
    "artStyle": "art_style",
    "colorPalette": "color_palette",
    "lighting": "lighting",
    "mood": "mood",
    "composition": "composition",
    "cameraLanguage": "camera_language",
    "materials": "materials",
    "era": "era",
    "visualKeywords": "visual_keywords",
    "negativePrompt": "negative_prompt",
}


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        value = " ".join(str(v) for v in value.values())
    elif isinstance(value, list):
        value = " ".join(str(v) for v in value)
    else:
        value = str(value)
    return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower()) if token}


def jaccard(left: Any, right: Any) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens and not right_tokens:
        return 0.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def compare_profiles(
    source_profile: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    dimension_scores: dict[str, float] = {}
    weighted_total = 0.0
    weight_total = 0.0

    for config_key, weight in weights.items():
        field = FIELD_MAP.get(config_key, config_key)
        left = source_profile.get(field)
        right = candidate_profile.get(field)
        score = jaccard(left, right)
        dimension_scores[field] = round(score, 4)
        weighted_total += score * float(weight)
        weight_total += float(weight)

    similarity = weighted_total / weight_total if weight_total else 0.0
    matched = [field for field, score in dimension_scores.items() if score >= 0.5]
    different = [field for field, score in dimension_scores.items() if score < 0.25]
    return {
        "similarity_score": round(similarity, 4),
        "dimension_scores": dimension_scores,
        "matched_dimensions": matched,
        "different_dimensions": different,
    }


def decision_for_score(score: float, thresholds: Mapping[str, float]) -> str:
    if score >= float(thresholds.get("existingStyle", 0.86)):
        return "existing_style"
    if score >= float(thresholds.get("styleBranch", 0.72)):
        return "style_branch"
    return "new_style"

