from __future__ import annotations

from typing import Any


def default_generation_params(config: Any) -> dict[str, Any]:
    generation = getattr(config, "data", {}).get("generation", {})
    params = generation.get("defaultParams", {})
    return dict(params) if isinstance(params, dict) else {}


def prompt_record_generation_params(prompt_record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(prompt_record, dict):
        return {}

    params = prompt_record.get("generation_params")
    if isinstance(params, dict):
        return dict(params)

    constraints = prompt_record.get("constraints")
    if isinstance(constraints, dict) and isinstance(constraints.get("generation_params"), dict):
        return dict(constraints["generation_params"])

    return {}


def merge_generation_params(config: Any, *sources: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_generation_params(config)
    for source in sources:
        if isinstance(source, dict):
            merged.update({key: value for key, value in source.items() if value not in (None, "")})
    return merged


def apply_prompt_generation_params(payload: dict[str, Any], config: Any) -> dict[str, Any]:
    payload["generation_params"] = merge_generation_params(config, prompt_record_generation_params(payload))
    return payload


def apply_generation_skill_params(payload: dict[str, Any], config: Any) -> dict[str, Any]:
    prompt_record = payload.get("prompt_record") if isinstance(payload.get("prompt_record"), dict) else None
    payload["skill_params"] = merge_generation_params(
        config,
        prompt_record_generation_params(prompt_record),
        payload.get("generation_params") if isinstance(payload.get("generation_params"), dict) else {},
        payload.get("skill_params") if isinstance(payload.get("skill_params"), dict) else {},
    )
    return payload
