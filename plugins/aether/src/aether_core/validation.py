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
    if "selected_assets" in payload and not isinstance(payload["selected_assets"], list):
        raise ValidationError("Field selected_assets must be a list")
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
    elif kind == "prompt":
        validate_prompt_record(payload)
    elif kind == "generation":
        validate_generation_run(payload)
    else:
        raise ValidationError(f"Unknown validation kind: {kind}")
