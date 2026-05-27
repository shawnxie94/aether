from __future__ import annotations

import re
from typing import Any

from .storage import AetherStore


TYPE_QUOTAS = {
    "style": 1,
    "color_palette": 1,
    "lighting": 1,
    "composition": 1,
    "camera": 1,
    "mood": 2,
    "scene": 1,
    "texture": 2,
    "character": 1,
    "prop_symbol": 2,
    "shape_line": 1,
    "negative_rule": 1,
}

PLAN_KEYS = {
    "style": "style",
    "color_palette": "color",
    "lighting": "lighting",
    "composition": "composition",
    "camera": "camera",
    "mood": "mood",
    "scene": "scene",
    "texture": "texture",
    "character": "character",
    "prop_symbol": "symbols",
    "shape_line": "shape_line",
    "negative_rule": "negative_rules",
}

CONFLICT_RULES = [
    ({"minimal", "negative space", "empty"}, {"dense", "maximalist", "crowded"}, "minimal composition conflicts with dense visual detail"),
    ({"warm", "healing", "cozy"}, {"cold", "oppressive", "harsh"}, "warm healing mood conflicts with cold oppressive lighting"),
    ({"photorealistic", "realistic photo", "cinematic photo"}, {"crayon", "pastel", "hand-drawn"}, "photoreal rendering conflicts with hand-drawn material language"),
    ({"low saturation", "muted"}, {"high saturation", "neon"}, "muted color palette conflicts with high-saturation neon treatment"),
]


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower()) if len(token) >= 2}


def _asset_text(asset: dict[str, Any]) -> str:
    parts: list[str] = [
        asset.get("name", ""),
        asset.get("summary", ""),
        " ".join(str(item) for item in asset.get("tags", [])),
        " ".join(str(item) for item in asset.get("prompt_fragments", [])),
    ]
    profile = asset.get("profile", {})
    if isinstance(profile, dict):
        parts.extend(str(value) for value in profile.values())
    return " ".join(parts)


def _selected_asset_id(selected: Any) -> str:
    if isinstance(selected, str):
        return selected
    if isinstance(selected, dict):
        value = selected.get("asset_id") or selected.get("id")
        return value if isinstance(value, str) else ""
    return ""


def _quality_score(store: AetherStore, asset_id: str) -> float:
    return float(store.visual_asset_quality(asset_id)["score"])


def _asset_score(
    store: AetherStore,
    asset: dict[str, Any],
    prompt_tokens: set[str],
    query_tokens: set[str],
    explicit_asset_ids: set[str],
    selected_ids: set[str],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    asset_id = asset["id"]
    if asset_id in explicit_asset_ids:
        score += 100.0
        reasons.append("explicitly requested")

    asset_tokens = _tokens(_asset_text(asset))
    prompt_overlap = sorted(prompt_tokens & asset_tokens)
    query_overlap = sorted(query_tokens & asset_tokens)
    if prompt_overlap:
        score += min(15.0, len(prompt_overlap) * 3.0)
        reasons.append("matches prompt terms: " + ", ".join(prompt_overlap[:4]))
    if query_overlap:
        score += min(12.0, len(query_overlap) * 3.0)
        reasons.append("matches query terms: " + ", ".join(query_overlap[:4]))

    quality = _quality_score(store, asset_id)
    score += quality * 10.0
    reasons.append(f"quality score {quality:.2f}")

    compatible = {str(value) for value in asset.get("compatible_with", [])}
    avoid = {str(value) for value in asset.get("avoid_with", [])}
    if selected_ids & compatible:
        score += 6.0
        reasons.append("compatible with selected assets")
    if selected_ids & avoid:
        score -= 30.0
        reasons.append("conflicts with selected assets")
    return score, reasons


def _detect_conflicts(selected_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    selected_ids = {asset["id"] for asset in selected_assets}
    for asset in selected_assets:
        avoid = {str(value) for value in asset.get("avoid_with", [])}
        for other_id in sorted(selected_ids & avoid):
            conflicts.append(
                {
                    "asset_id": asset["id"],
                    "conflicts_with": other_id,
                    "reason": "avoid_with relationship",
                    "resolution": "drop the lower-priority optional asset unless the user explicitly requested both",
                }
            )

    combined_text = " ".join(_asset_text(asset).lower() for asset in selected_assets)
    for left_terms, right_terms, reason in CONFLICT_RULES:
        if any(term in combined_text for term in left_terms) and any(term in combined_text for term in right_terms):
            conflicts.append(
                {
                    "asset_id": "",
                    "conflicts_with": "",
                    "reason": reason,
                    "resolution": "preserve explicit user constraints, keep the core style asset, and drop optional enhancement assets",
                }
            )
    return conflicts


def compose_prompt(
    store: AetherStore,
    source_prompt: str,
    *,
    explicit_asset_ids: list[str] | None = None,
    query: str = "",
    aspect_ratio: str | None = None,
    target_generation_skill: str | None = None,
    default_generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit_asset_ids = explicit_asset_ids or []
    explicit_set = set(explicit_asset_ids)
    prompt_tokens = _tokens(source_prompt)
    query_tokens = _tokens(query)
    active_assets = store.list_visual_assets(status="active", limit=None)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    reasons_by_id: dict[str, list[str]] = {}

    for asset_id in explicit_asset_ids:
        asset = store.get_visual_asset(asset_id)
        if asset and asset["status"] != "archived":
            selected.append(asset)
            selected_ids.add(asset["id"])
            reasons_by_id[asset["id"]] = ["explicitly requested"]

    for asset_type, quota in TYPE_QUOTAS.items():
        current_count = sum(1 for asset in selected if asset["type"] == asset_type)
        if current_count >= quota:
            continue
        candidates = [asset for asset in active_assets if asset["type"] == asset_type and asset["id"] not in selected_ids]
        scored = [
            (_asset_score(store, asset, prompt_tokens, query_tokens, explicit_set, selected_ids), asset)
            for asset in candidates
        ]
        scored.sort(key=lambda item: item[0][0], reverse=True)
        for (score, reasons), asset in scored[: max(0, quota - current_count)]:
            if score <= 4.0 and asset_type not in ("negative_rule",):
                continue
            selected.append(asset)
            selected_ids.add(asset["id"])
            reasons_by_id[asset["id"]] = reasons

    conflicts = _detect_conflicts(selected)
    selected_assets = [
        {
            "type": asset["type"],
            "asset_id": asset["id"],
            "name": asset["name"],
            "reason": "; ".join(reasons_by_id.get(asset["id"], [])),
        }
        for asset in selected
    ]

    prompt_fragments: list[str] = []
    negative_fragments: list[str] = []
    for asset in selected:
        prompt_fragments.extend(str(fragment) for fragment in asset.get("prompt_fragments", []) if fragment)
        negative_fragments.extend(str(fragment) for fragment in asset.get("negative_fragments", []) if fragment)

    generation_params = dict(default_generation_params or {})
    if aspect_ratio:
        generation_params["aspectRatio"] = aspect_ratio
    elif "aspectRatio" not in generation_params:
        for asset in selected:
            ratios = asset.get("recommended_aspect_ratios", [])
            if ratios:
                generation_params["aspectRatio"] = ratios[0]
                break
    generation_params.setdefault("aspectRatio", "1:1")

    composition_plan: dict[str, Any] = {
        "subject": source_prompt,
        "scene": "",
        "style": "",
        "color": "",
        "lighting": "",
        "composition": "",
        "camera": "",
        "mood": [],
        "texture": [],
        "character": "",
        "symbols": [],
        "shape_line": "",
        "negative_rules": [],
    }
    for asset in selected:
        key = PLAN_KEYS.get(asset["type"], asset["type"])
        summary = asset.get("summary") or asset.get("name", "")
        if isinstance(composition_plan.get(key), list):
            composition_plan[key].append(summary)
        else:
            composition_plan[key] = summary

    refined_parts = [source_prompt]
    refined_parts.extend(fragment for fragment in prompt_fragments if fragment not in refined_parts)
    negative_parts = []
    for fragment in negative_fragments:
        if fragment not in negative_parts:
            negative_parts.append(fragment)

    assumptions = [
        "Selected visual assets were recalled from active assets using explicit ids, prompt/query overlap, compatibility, and generation quality.",
        f"Aspect ratio set to {generation_params['aspectRatio']}.",
    ]
    if conflicts:
        assumptions.append("Conflicts were detected; preserve explicit user constraints and core style before optional assets.")

    return {
        "source_prompt": source_prompt,
        "target_generation_skill": target_generation_skill,
        "selected_assets": selected_assets,
        "constraints": {
            "selected_assets": selected_assets,
            "conflicts": conflicts,
        },
        "intent_analysis": {
            "source_prompt": source_prompt,
            "query": query,
            "prompt_terms": sorted(prompt_tokens),
            "query_terms": sorted(query_tokens),
        },
        "composition_plan": composition_plan,
        "refined_prompt": ", ".join(refined_parts),
        "negative_prompt": ", ".join(negative_parts),
        "generation_params": generation_params,
        "variants": [],
        "assumptions": assumptions,
        "conflicts": conflicts,
    }
