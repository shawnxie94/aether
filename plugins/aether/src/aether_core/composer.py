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


def _visual_rule_text(rule: Any) -> str:
    if isinstance(rule, str):
        return rule
    if not isinstance(rule, dict):
        return ""
    key = rule.get("key")
    value = rule.get("value")
    if isinstance(value, list):
        value_text = ", ".join(str(item) for item in value if item)
    elif isinstance(value, str):
        value_text = value
    else:
        value_text = ""
    if not key or not value_text:
        return ""
    return f"{key}: {value_text}"


def _profile_value_texts(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [text for item in value.values() for text in _profile_value_texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in _profile_value_texts(item)]
    if isinstance(value, (str, int, float, bool)):
        return [str(value)]
    return []


def _asset_text(asset: dict[str, Any]) -> str:
    parts: list[str] = [
        asset.get("name", ""),
        asset.get("summary", ""),
        " ".join(str(item) for item in asset.get("tags", [])),
        " ".join(str(item) for item in asset.get("prompt_fragments", [])),
    ]
    profile = asset.get("profile", {})
    if isinstance(profile, dict):
        parts.extend(text for value in profile.values() for text in _profile_value_texts(value))
    return " ".join(parts)


def _selected_asset_id(selected: Any) -> str:
    if isinstance(selected, str):
        return selected
    if isinstance(selected, dict):
        value = selected.get("asset_id") or selected.get("id")
        return value if isinstance(value, str) else ""
    return ""


def _intent_sketch(source_prompt: str, query: str = "") -> dict[str, Any]:
    terms = sorted(_tokens(" ".join([source_prompt, query])))
    return {
        "subject": source_prompt,
        "scene": "",
        "action": "",
        "mood": [],
        "style_intent": [],
        "composition_intent": [],
        "color_lighting_intent": [],
        "negative_intent": [],
        "query_terms": terms,
        "user_constraints": [],
        "assumptions": [],
    }


def _quality_score(store: AetherStore, asset_id: str) -> float:
    return float(store.visual_asset_quality(asset_id)["score"])


def _asset_score(
    store: AetherStore,
    asset: dict[str, Any],
    prompt_tokens: set[str],
    query_tokens: set[str],
    explicit_asset_ids: set[str],
    selected_ids: set[str],
    boosted_ids: dict[str, list[str]] | None = None,
    avoided_ids: set[str] | None = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    asset_id = asset["id"]
    boosted_ids = boosted_ids or {}
    avoided_ids = avoided_ids or set()
    if asset_id in explicit_asset_ids:
        score += 100.0
        reasons.append("explicitly requested")
    if asset_id in boosted_ids:
        score += 18.0
        reasons.extend(boosted_ids[asset_id])
    if asset_id in avoided_ids and asset_id not in explicit_asset_ids:
        score -= 60.0
        reasons.append("discouraged by selected system or recipe")

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
    system_ids: list[str] | None = None,
    recipe_ids: list[str] | None = None,
    query: str = "",
    aspect_ratio: str | None = None,
    target_generation_skill: str | None = None,
    default_generation_params: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit_asset_ids = explicit_asset_ids or []
    system_ids = system_ids or []
    recipe_ids = recipe_ids or []
    explicit_set = set(explicit_asset_ids)
    intent_sketch = _intent_sketch(source_prompt, query)
    recall_query = " ".join([source_prompt, query, " ".join(intent_sketch["query_terms"])])
    recalled_systems: list[dict[str, Any]] = []
    recalled_recipes: list[dict[str, Any]] = []
    recalled_assets: list[dict[str, Any]] = []
    if not system_ids:
        recalled_systems = [
            item
            for item in store.hybrid_recall("visual_system", recall_query, config=config, limit=3)
            if item["score"] >= 0.02
        ]
        system_ids = [item["system_id"] for item in recalled_systems[:1]]
    if not recipe_ids:
        recalled_recipes = [
            item
            for item in store.hybrid_recall("recipe", recall_query, config=config, limit=3)
            if item["score"] >= 0.02
        ]
        recipe_ids = [item["recipe_id"] for item in recalled_recipes[:1]]
    recalled_assets = [
        item
        for item in store.hybrid_recall("visual_asset", recall_query, config=config, limit=12)
        if item["score"] >= 0.02
    ]
    recalled_system_reasons = {item["system_id"]: item for item in recalled_systems}
    recalled_recipe_reasons = {item["recipe_id"]: item for item in recalled_recipes}
    prompt_tokens = _tokens(source_prompt)
    query_tokens = _tokens(query)
    active_assets = store.list_visual_assets(status="active", limit=None)
    active_by_id = {asset["id"]: asset for asset in active_assets}

    selected_systems: list[dict[str, Any]] = []
    selected_recipes: list[dict[str, Any]] = []
    forced_asset_reasons: dict[str, list[str]] = {}
    boosted_asset_reasons: dict[str, list[str]] = {}
    avoided_asset_ids: set[str] = set()
    system_visual_rules: list[str] = []
    system_avoid_rules: list[str] = []
    recipe_composition_rules: list[str] = []
    recipe_negative_rules: list[str] = []

    for item in recalled_assets:
        boosted_asset_reasons.setdefault(item["asset_id"], []).append(
            f"recalled asset score {item['score']:.2f}"
        )

    for system_id in system_ids:
        system = store.get_visual_system(system_id)
        if not system or system["status"] == "archived":
            continue
        selected_systems.append(
            {
                "system_id": system["id"],
                "kind": system["kind"],
                "name": system["name"],
                "visual_rules": system.get("visual_rules", []),
                "avoid_rules": system.get("avoid_rules", []),
                "reason": "recalled visual system" if system["id"] in recalled_system_reasons else "requested visual system",
                "recall": recalled_system_reasons.get(system["id"]),
            }
        )
        system_visual_rules.extend(
            text for rule in system.get("visual_rules", []) if (text := _visual_rule_text(rule))
        )
        system_avoid_rules.extend(str(rule) for rule in system.get("avoid_rules", []) if rule)
        for relation in system.get("assets", []):
            asset_id = relation["asset_id"]
            role = relation.get("role", "optional")
            reason = f"{system['kind']} system {system['name']} relation: {role}"
            if role == "core":
                forced_asset_reasons.setdefault(asset_id, []).append(reason)
            elif role == "optional":
                boosted_asset_reasons.setdefault(asset_id, []).append(reason)
            elif role == "avoid":
                avoided_asset_ids.add(asset_id)

    for recipe_id in recipe_ids:
        recipe = store.get_recipe(recipe_id)
        if not recipe or recipe["status"] == "archived":
            continue
        selected_recipes.append(
            {
                "recipe_id": recipe["id"],
                "name": recipe["name"],
                "composition_rules": recipe.get("composition_rules", []),
                "recommended_aspect_ratios": recipe.get("recommended_aspect_ratios", []),
                "reason": "recalled recipe" if recipe["id"] in recalled_recipe_reasons else "requested recipe",
                "recall": recalled_recipe_reasons.get(recipe["id"]),
            }
        )
        for rule in recipe.get("composition_rules", []):
            text = _visual_rule_text(rule)
            if not text:
                continue
            if isinstance(rule, dict) and rule.get("key") == "negative_constraints":
                recipe_negative_rules.append(text)
            else:
                recipe_composition_rules.append(text)
        for system_id in recipe.get("parent_system_ids", []):
            if system_id not in system_ids:
                system = store.get_visual_system(system_id)
                if system and system["status"] != "archived":
                    selected_systems.append(
                        {
                            "system_id": system["id"],
                            "kind": system["kind"],
                            "name": system["name"],
                            "visual_rules": system.get("visual_rules", []),
                            "avoid_rules": system.get("avoid_rules", []),
                            "reason": f"parent system of recipe {recipe['name']}",
                        }
                    )
                    system_visual_rules.extend(
                        text for rule in system.get("visual_rules", []) if (text := _visual_rule_text(rule))
                    )
                    system_avoid_rules.extend(str(rule) for rule in system.get("avoid_rules", []) if rule)
                    for relation in system.get("assets", []):
                        asset_id = relation["asset_id"]
                        role = relation.get("role", "optional")
                        reason = f"{system['kind']} system {system['name']} relation: {role}"
                        if role == "core":
                            forced_asset_reasons.setdefault(asset_id, []).append(reason)
                        elif role == "optional":
                            boosted_asset_reasons.setdefault(asset_id, []).append(reason)
                        elif role == "avoid":
                            avoided_asset_ids.add(asset_id)
        for relation in recipe.get("assets", []):
            asset_id = relation["asset_id"]
            role = relation.get("role", "optional")
            reason = f"recipe {recipe['name']} relation: {role}"
            if role == "core":
                forced_asset_reasons.setdefault(asset_id, []).append(reason)
            elif role == "optional":
                boosted_asset_reasons.setdefault(asset_id, []).append(reason)
            elif role == "avoid":
                avoided_asset_ids.add(asset_id)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    reasons_by_id: dict[str, list[str]] = {}

    for asset_id in explicit_asset_ids:
        asset = store.get_visual_asset(asset_id)
        if asset and asset["status"] != "archived":
            selected.append(asset)
            selected_ids.add(asset["id"])
            reasons_by_id[asset["id"]] = ["explicitly requested"]

    for asset_id, reasons in sorted(forced_asset_reasons.items(), key=lambda item: item[0]):
        if asset_id in selected_ids:
            reasons_by_id[asset_id].extend(reasons)
            continue
        asset = active_by_id.get(asset_id) or store.get_visual_asset(asset_id)
        if asset and asset["status"] == "active":
            selected.append(asset)
            selected_ids.add(asset["id"])
            reasons_by_id[asset["id"]] = reasons

    for asset_type, quota in TYPE_QUOTAS.items():
        current_count = sum(1 for asset in selected if asset["type"] == asset_type)
        if current_count >= quota:
            continue
        candidates = [
            asset
            for asset in active_assets
            if asset["type"] == asset_type
            and asset["id"] not in selected_ids
            and (asset["id"] not in avoided_asset_ids or asset["id"] in explicit_set)
        ]
        scored = [
            (
                _asset_score(
                    store,
                    asset,
                    prompt_tokens,
                    query_tokens,
                    explicit_set,
                    selected_ids,
                    boosted_asset_reasons,
                    avoided_asset_ids,
                ),
                asset,
            )
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
    else:
        selected_ratio = ""
        for recipe in selected_recipes:
            ratios = recipe.get("recommended_aspect_ratios", [])
            if ratios:
                selected_ratio = ratios[0]
                break
        if not selected_ratio:
            for asset in selected:
                ratios = asset.get("recommended_aspect_ratios", [])
                if ratios:
                    selected_ratio = ratios[0]
                    break
        if selected_ratio:
            generation_params["aspectRatio"] = selected_ratio
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
    if selected_systems:
        composition_plan["visual_systems"] = selected_systems
        composition_plan["system_rules"] = []
        for rule in system_visual_rules:
            if rule not in composition_plan["system_rules"]:
                composition_plan["system_rules"].append(rule)
    if selected_recipes:
        composition_plan["recipes"] = selected_recipes
        composition_plan["composition_rules"] = []
        for rule in recipe_composition_rules:
            if rule not in composition_plan["composition_rules"]:
                composition_plan["composition_rules"].append(rule)
    for asset in selected:
        key = PLAN_KEYS.get(asset["type"], asset["type"])
        summary = asset.get("summary") or asset.get("name", "")
        if isinstance(composition_plan.get(key), list):
            composition_plan[key].append(summary)
        else:
            composition_plan[key] = summary

    refined_parts = [source_prompt]
    for fragment in system_visual_rules:
        if fragment not in refined_parts:
            refined_parts.append(fragment)
    for fragment in recipe_composition_rules:
        if fragment not in refined_parts:
            refined_parts.append(fragment)
    refined_parts.extend(fragment for fragment in prompt_fragments if fragment not in refined_parts)
    negative_parts = []
    for fragment in system_avoid_rules:
        if fragment not in negative_parts:
            negative_parts.append(fragment)
    for fragment in recipe_negative_rules:
        if fragment not in negative_parts:
            negative_parts.append(fragment)
    for fragment in negative_fragments:
        if fragment not in negative_parts:
            negative_parts.append(fragment)

    assumptions = [
        "Selected visual assets were recalled from active assets using explicit ids, visual systems, recipes, prompt/query overlap, compatibility, and generation quality.",
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
            "selected_systems": selected_systems,
            "selected_recipes": selected_recipes,
            "avoided_asset_ids": sorted(avoided_asset_ids),
            "conflicts": conflicts,
        },
        "intent_sketch": intent_sketch,
        "recall_candidates": {
            "visual_systems": recalled_systems,
            "recipes": recalled_recipes,
            "visual_assets": recalled_assets,
        },
        "recall_strategy": {
            "mode": "hybrid" if config and config.get("embedding", {}).get("provider") not in (None, "", "disabled") else "lexical_relation",
            "semantic_enabled": bool(config and config.get("embedding", {}).get("provider") not in (None, "", "disabled")),
            "embedding_provider": (config or {}).get("embedding", {}).get("provider", "disabled"),
            "embedding_model": (config or {}).get("embedding", {}).get("model", ""),
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
