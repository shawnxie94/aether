from __future__ import annotations

from typing import Any

from .config import LoadedConfig
from .generation_params import apply_generation_skill_params
from .output_archiving import archive_generation_outputs, resolve_generation_relations
from .storage import AetherStore


def selected_assets_from_payload(payload: dict[str, Any]) -> list[Any]:
    """Return selected visual assets from a run or its prompt record."""

    if isinstance(payload.get("selected_assets"), list):
        return payload["selected_assets"]
    prompt_record = payload.get("prompt_record", {})
    if not isinstance(prompt_record, dict):
        return []
    if isinstance(prompt_record.get("selected_assets"), list):
        return prompt_record["selected_assets"]
    constraints = prompt_record.get("constraints", {})
    if isinstance(constraints, dict) and isinstance(constraints.get("selected_assets"), list):
        return constraints["selected_assets"]
    return []


def apply_visual_review_default(payload: dict[str, Any]) -> dict[str, Any]:
    """Make an unreviewed or failed run auditable before persistence."""

    if isinstance(payload.get("visual_review"), dict) and payload["visual_review"]:
        return payload
    if payload.get("status") not in {"generated", "edited"}:
        error_text = str(payload.get("error") or "")
        deviations = []
        if error_text:
            deviations.append(f"infra error: {error_text[:200]}")
        else:
            deviations.append("no visual review: attempt did not reach generated or edited state")
        payload["visual_review"] = {
            "reviewed": False,
            "style_consistency": "not_reviewed",
            "score": None,
            "recipe_fidelity": "not_reviewed",
            "recipe_fidelity_score": None,
            "subject_consistency": "not_reviewed",
            "subject_consistency_score": None,
            "matched_traits": [],
            "matched_signature_traits": [],
            "matched_subject_traits": [],
            "deviations": deviations,
            "recommendation": "use",
            "suggested_revision": "",
            "suggested_edit_instruction": "",
            "localized_deviations": [],
        }
        return payload

    reason = "Visual review was not provided before recording this generated output."
    if not payload.get("outputs"):
        reason = "Visual review was skipped because no output image path was provided."
    elif not selected_assets_from_payload(payload):
        reason = "Visual review was skipped because no selected visual assets were provided."

    payload["visual_review"] = {
        "reviewed": False,
        "style_consistency": "not_reviewed",
        "score": None,
        "recipe_fidelity": "not_reviewed",
        "recipe_fidelity_score": None,
        "subject_consistency": "not_reviewed",
        "subject_consistency_score": None,
        "matched_traits": [],
        "matched_signature_traits": [],
        "matched_subject_traits": [],
        "deviations": [reason],
        "recommendation": "use",
        "suggested_revision": "",
        "suggested_edit_instruction": "",
        "localized_deviations": [],
    }
    return payload


def prepare_generation_payload(
    config: LoadedConfig,
    store: AetherStore,
    payload: dict[str, Any],
    *,
    apply_review_default: bool = False,
) -> dict[str, Any]:
    """Normalize one generation command before the storage write.

    The steps deliberately stay in the application boundary: parameter
    precedence, optional review defaults, output archiving, and relation
    expansion. Storage performs the existing final payload validation. The
    storage layer receives one complete payload and
    does not perform filesystem or schema orchestration.
    """

    payload = apply_generation_skill_params(payload, config)
    if apply_review_default:
        payload = apply_visual_review_default(payload)
    payload = archive_generation_outputs(config, store, payload)
    return resolve_generation_relations(payload, store)


def record_generation_run(
    config: LoadedConfig,
    store: AetherStore,
    payload: dict[str, Any],
    *,
    apply_review_default: bool = False,
) -> dict[str, Any]:
    """Prepare and persist one generation run."""

    prepared = prepare_generation_payload(
        config,
        store,
        payload,
        apply_review_default=apply_review_default,
    )
    return store.create_generation_run(prepared)
