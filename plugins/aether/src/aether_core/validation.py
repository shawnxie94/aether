from __future__ import annotations

from typing import Any


class ValidationError(ValueError):
    pass


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


def validate_prompt_record(payload: dict[str, Any]) -> None:
    _require(payload, "source_prompt", str)
    _require(payload, "refined_prompt", str)
    if "generation_params" in payload and not isinstance(payload["generation_params"], dict):
        raise ValidationError("Field generation_params must be a dict")
    if "variants" in payload and not isinstance(payload["variants"], list):
        raise ValidationError("Field variants must be a list")
    if "assumptions" in payload and not isinstance(payload["assumptions"], list):
        raise ValidationError("Field assumptions must be a list")


def validate_generation_run(payload: dict[str, Any]) -> None:
    _require(payload, "refined_prompt", str)
    _require(payload, "generation_skill", str)
    if "outputs" in payload and not isinstance(payload["outputs"], list):
        raise ValidationError("Field outputs must be a list")
    if "skill_params" in payload and not isinstance(payload["skill_params"], dict):
        raise ValidationError("Field skill_params must be a dict")
    if "visual_review" in payload and not isinstance(payload["visual_review"], dict):
        raise ValidationError("Field visual_review must be a dict")


def validate_payload(kind: str, payload: dict[str, Any]) -> None:
    if kind == "style":
        validate_style(payload)
    elif kind == "prompt":
        validate_prompt_record(payload)
    elif kind == "generation":
        validate_generation_run(payload)
    else:
        raise ValidationError(f"Unknown validation kind: {kind}")
