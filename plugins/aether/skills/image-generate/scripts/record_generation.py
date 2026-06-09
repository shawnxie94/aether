#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.config import ensure_configured_dirs, load_config
from aether_core.generation_params import apply_generation_skill_params
from aether_core.output_archiving import archive_generation_outputs
from aether_core.storage import AetherStore
from aether_core.validation import validate_generation_run


def apply_retry_metadata(payload: dict, args: argparse.Namespace) -> dict:
    retry_fields = {
        "attempt": args.attempt,
        "max_attempts": args.max_attempts,
        "retry_of": args.retry_of,
        "retryable": None if args.retryable is None else args.retryable == "true",
    }
    retry_metadata = {key: value for key, value in retry_fields.items() if value is not None}
    if not retry_metadata:
        return payload

    meta = payload.setdefault("skill_result_meta", {})
    meta["retry"] = {**meta.get("retry", {}), **retry_metadata}
    return payload


def selected_assets_from_payload(payload: dict) -> list:
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


def apply_visual_review_default(payload: dict) -> dict:
    if isinstance(payload.get("visual_review"), dict) and payload["visual_review"]:
        return payload
    if payload.get("status") not in {"generated", "edited"}:
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
        # New fidelity breakdown. Both default to not_reviewed so historical
        # runs do not silently count as either a high or low recipe match.
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Generation run JSON path, or '-' for stdin.")
    parser.add_argument("--liked", choices=["true", "false"])
    parser.add_argument("--notes")
    parser.add_argument("--attempt", type=int, help="One-based generation attempt number.")
    parser.add_argument("--max-attempts", type=int, help="Maximum attempts planned for this generation request.")
    parser.add_argument("--retry-of", help="Generation run id or logical request id this attempt retries.")
    parser.add_argument("--retryable", choices=["true", "false"], help="Whether the failure should be considered retryable.")
    args = parser.parse_args()

    config = load_config()
    ensure_configured_dirs(config)
    payload = json.load(sys.stdin) if args.json == "-" else json.loads(Path(args.json).read_text(encoding="utf-8"))
    payload = apply_generation_skill_params(payload, config)
    payload = apply_retry_metadata(payload, args)
    payload = apply_visual_review_default(payload)
    validate_generation_run(payload)
    store = AetherStore(config.database_path)
    store.init()
    payload = archive_generation_outputs(config, store, payload)
    record = store.create_generation_run(payload)
    if args.liked is not None or args.notes:
        feedback = {}
        if args.liked is not None:
            feedback["liked"] = args.liked == "true"
        if args.notes:
            feedback["notes"] = args.notes
        status = "liked" if feedback.get("liked") is True else "rejected" if feedback.get("liked") is False else None
        record = store.update_generation_feedback(record["id"], feedback, status)
    json.dump(record, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
