from __future__ import annotations

from typing import Any


class ValidationError(ValueError):
    pass


VISUAL_ASSET_TYPES = {
    "style",
    "color_palette",
    "lighting",
    "composition",
    "camera",
    "mood",
    "scene",
    "texture",
    "character",
    "prop_symbol",
    "shape_line",
    "negative_rule",
}

VISUAL_ASSET_CANDIDATE_DECISIONS = {
    "existing_asset",
    "asset_variant",
    "new_asset",
    "ignore",
}

VISUAL_SYSTEM_KINDS = {
    "worldview",
    "genre",
    "series",
    "art_direction",
}

RELATION_ROLES = {
    "core",
    "optional",
    "avoid",
    "reference_only",
}


def _require(payload: dict[str, Any], field: str, expected_type: type | tuple[type, ...]) -> None:
    if field not in payload:
        raise ValidationError(f"Missing required field: {field}")
    if not isinstance(payload[field], expected_type):
        raise ValidationError(f"Field {field} must be {expected_type}")


def validate_style(payload: dict[str, Any]) -> None:
    _require(payload, "name", str)
    if "style_profile" in payload and not isinstance(payload["style_profile"], dict):
        raise ValidationError("Field style_profile must be a dict")
    if "tags" in payload and not isinstance(payload["tags"], list):
        raise ValidationError("Field tags must be a list")
    if "source_references" in payload and not isinstance(payload["source_references"], list):
        raise ValidationError("Field source_references must be a list")


def validate_visual_asset(payload: dict[str, Any]) -> None:
    _require(payload, "type", str)
    _require(payload, "name", str)
    if payload["type"] not in VISUAL_ASSET_TYPES:
        raise ValidationError(f"Field type must be one of: {', '.join(sorted(VISUAL_ASSET_TYPES))}")
    if "tags" in payload and not isinstance(payload["tags"], list):
        raise ValidationError("Field tags must be a list")
    if "profile" in payload and not isinstance(payload["profile"], dict):
        raise ValidationError("Field profile must be a dict")
    for field in [
        "source_references",
        "prompt_fragments",
        "negative_fragments",
        "compatible_with",
        "avoid_with",
        "recommended_aspect_ratios",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")


def validate_visual_asset_candidate(payload: dict[str, Any]) -> None:
    if "candidate_assets" in payload:
        if not isinstance(payload["candidate_assets"], list):
            raise ValidationError("Field candidate_assets must be a list")
        for candidate in payload["candidate_assets"]:
            if not isinstance(candidate, dict):
                raise ValidationError("Each candidate asset must be an object")
            validate_visual_asset_candidate(candidate)
        if "recipe_candidates" in payload:
            if not isinstance(payload["recipe_candidates"], list):
                raise ValidationError("Field recipe_candidates must be a list")
            for recipe in payload["recipe_candidates"]:
                if not isinstance(recipe, dict):
                    raise ValidationError("Each recipe candidate must be an object")
                validate_recipe_candidate(recipe)
        if "visual_system_candidates" in payload:
            if not isinstance(payload["visual_system_candidates"], list):
                raise ValidationError("Field visual_system_candidates must be a list")
            for system in payload["visual_system_candidates"]:
                if not isinstance(system, dict):
                    raise ValidationError("Each visual system candidate must be an object")
                validate_visual_system_candidate(system)
        return
    _require(payload, "type", str)
    _require(payload, "name", str)
    if payload["type"] not in VISUAL_ASSET_TYPES:
        raise ValidationError(f"Field type must be one of: {', '.join(sorted(VISUAL_ASSET_TYPES))}")
    if "reuse_score" in payload and not isinstance(payload["reuse_score"], (int, float)):
        raise ValidationError("Field reuse_score must be a number")
    if "decision" in payload and payload["decision"] not in VISUAL_ASSET_CANDIDATE_DECISIONS:
        raise ValidationError(
            f"Field decision must be one of: {', '.join(sorted(VISUAL_ASSET_CANDIDATE_DECISIONS))}"
        )
    for field in [
        "tags",
        "source_references",
        "source_reference_ids",
        "prompt_fragments",
        "negative_fragments",
        "compatible_with",
        "avoid_with",
        "recommended_aspect_ratios",
        "similar_candidates",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "profile" in payload and not isinstance(payload["profile"], dict):
        raise ValidationError("Field profile must be a dict")


def validate_visual_system(payload: dict[str, Any]) -> None:
    _require(payload, "kind", str)
    _require(payload, "name", str)
    if payload["kind"] not in VISUAL_SYSTEM_KINDS:
        raise ValidationError(f"Field kind must be one of: {', '.join(sorted(VISUAL_SYSTEM_KINDS))}")
    for field in ["tags", "visual_rules", "avoid_rules", "source_reference_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise ValidationError("Field metadata must be a dict")


def validate_asset_relation(payload: dict[str, Any]) -> None:
    _require(payload, "asset_id", str)
    if "role" in payload and payload["role"] not in RELATION_ROLES:
        raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
    if "weight" in payload and not isinstance(payload["weight"], (int, float)):
        raise ValidationError("Field weight must be a number")


def validate_recipe(payload: dict[str, Any]) -> None:
    _require(payload, "name", str)
    for field in [
        "parent_system_ids",
        "use_cases",
        "required_asset_types",
        "recommended_aspect_ratios",
        "source_reference_ids",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "confidence" in payload and not isinstance(payload["confidence"], (int, float)):
        raise ValidationError("Field confidence must be a number")
    for asset_type in payload.get("required_asset_types", []):
        if asset_type not in VISUAL_ASSET_TYPES:
            raise ValidationError(f"Field required_asset_types contains unsupported type: {asset_type}")


def validate_recipe_asset(payload: dict[str, Any]) -> None:
    validate_asset_relation(payload)


def validate_recipe_candidate(payload: dict[str, Any]) -> None:
    validate_recipe(payload)
    for field in ["candidate_asset_ids", "core_candidate_asset_ids", "optional_candidate_asset_ids", "avoid_candidate_asset_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "recipe_assets" in payload:
        if not isinstance(payload["recipe_assets"], list):
            raise ValidationError("Field recipe_assets must be a list")
        for relation in payload["recipe_assets"]:
            if not isinstance(relation, dict):
                raise ValidationError("Each recipe asset relation must be an object")
            if "candidate_asset_id" not in relation and "asset_id" not in relation:
                raise ValidationError("Recipe candidate relation requires candidate_asset_id or asset_id")
            if "role" in relation and relation["role"] not in RELATION_ROLES:
                raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
            if "weight" in relation and not isinstance(relation["weight"], (int, float)):
                raise ValidationError("Field weight must be a number")


def validate_visual_system_candidate(payload: dict[str, Any]) -> None:
    validate_visual_system(payload)
    for field in ["candidate_asset_ids", "core_candidate_asset_ids", "optional_candidate_asset_ids", "avoid_candidate_asset_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    for field in ["candidate_asset_relations", "existing_asset_relations", "related_existing_assets"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    for relation in payload.get("candidate_asset_relations", []):
        if not isinstance(relation, dict):
            raise ValidationError("Each candidate asset relation must be an object")
        if "candidate_asset_id" not in relation:
            raise ValidationError("Candidate asset relation requires candidate_asset_id")
        if "role" in relation and relation["role"] not in RELATION_ROLES:
            raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
        if "weight" in relation and not isinstance(relation["weight"], (int, float)):
            raise ValidationError("Field weight must be a number")
    for relation in payload.get("existing_asset_relations", []):
        if not isinstance(relation, dict):
            raise ValidationError("Each existing asset relation must be an object")
        validate_asset_relation(relation)


def validate_prompt_record(payload: dict[str, Any]) -> None:
    _require(payload, "source_prompt", str)
    _require(payload, "refined_prompt", str)
    if "selected_assets" in payload and not isinstance(payload["selected_assets"], list):
        raise ValidationError("Field selected_assets must be a list")
    if "generation_params" in payload and not isinstance(payload["generation_params"], dict):
        raise ValidationError("Field generation_params must be a dict")
    if "composition_plan" in payload and not isinstance(payload["composition_plan"], dict):
        raise ValidationError("Field composition_plan must be a dict")
    if "variants" in payload and not isinstance(payload["variants"], list):
        raise ValidationError("Field variants must be a list")
    if "assumptions" in payload and not isinstance(payload["assumptions"], list):
        raise ValidationError("Field assumptions must be a list")
    if "conflicts" in payload and not isinstance(payload["conflicts"], list):
        raise ValidationError("Field conflicts must be a list")


def validate_generation_run(payload: dict[str, Any]) -> None:
    _require(payload, "refined_prompt", str)
    _require(payload, "generation_skill", str)
    if "mode" in payload and payload["mode"] not in {"generate", "edit"}:
        raise ValidationError("Field mode must be generate or edit")
    if "selected_assets" in payload and not isinstance(payload["selected_assets"], list):
        raise ValidationError("Field selected_assets must be a list")
    if "edit_regions" in payload and not isinstance(payload["edit_regions"], list):
        raise ValidationError("Field edit_regions must be a list")
    if "outputs" in payload and not isinstance(payload["outputs"], list):
        raise ValidationError("Field outputs must be a list")
    if "skill_params" in payload and not isinstance(payload["skill_params"], dict):
        raise ValidationError("Field skill_params must be a dict")
    if "visual_review" in payload and not isinstance(payload["visual_review"], dict):
        raise ValidationError("Field visual_review must be a dict")


def validate_payload(kind: str, payload: dict[str, Any]) -> None:
    if kind in ("visual_asset", "visual-asset"):
        validate_visual_asset(payload)
    elif kind in ("visual_asset_candidate", "visual-asset-candidate"):
        validate_visual_asset_candidate(payload)
    elif kind in ("visual_system", "visual-system"):
        validate_visual_system(payload)
    elif kind in ("recipe",):
        validate_recipe(payload)
    elif kind == "prompt":
        validate_prompt_record(payload)
    elif kind == "generation":
        validate_generation_run(payload)
    else:
        raise ValidationError(f"Unknown validation kind: {kind}")
