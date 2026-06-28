#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
        # Failure path: still leave an auditable visual_review record so
        # retry history can be inspected. The breakdown fields are all
        # "not_reviewed" so the failure does not count as a fidelity or
        # subject signal; only the deviations list carries the cause.
        error_text = ""
        if payload.get("error"):
            error_text = str(payload.get("error"))
        deviations = []
        if error_text:
            deviations.append(f"infra error: {error_text[:200]}")
        else:
            deviations.append(
                "no visual review: attempt did not reach generated or edited state"
            )
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


def _candidate_payload(candidate: dict) -> dict:
    payload = candidate.get("payload", {}) if isinstance(candidate, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _format_values(values: list) -> str:
    clean = [str(value) for value in values if value]
    return "、".join(clean) if clean else "未指定"


def _format_candidate_line(candidate: dict, kind: str) -> str:
    payload = _candidate_payload(candidate)
    name = payload.get("name") or f"{kind} candidate"
    summary = payload.get("summary") or payload.get("reason") or "暂无摘要"
    status = candidate.get("status") or payload.get("status") or "pending"
    if kind == "Recipe":
        details = _format_values(payload.get("required_asset_types", []))
        return f"- {name}：{summary}；资产类型 {details}；状态 {status}"
    details = _format_values([payload.get("kind"), *payload.get("tags", [])])
    return f"- {name}：{summary}；系统类型/标签 {details}；状态 {status}"


def build_reuse_suggestion_message(record: dict) -> str:
    suggestions = record.get("reuse_suggestions", {})
    if not isinstance(suggestions, dict):
        return ""
    recipe_candidates = suggestions.get("recipe_candidates") or []
    system_candidates = suggestions.get("visual_system_candidates") or []
    if not recipe_candidates and not system_candidates:
        return ""

    lines = [
        "这次生成已经形成可复用沉淀候选。",
        "",
        "**建议保存为 Recipe（组合方式）**",
    ]
    if recipe_candidates:
        lines.extend(_format_candidate_line(candidate, "Recipe") for candidate in recipe_candidates)
    else:
        lines.append("- 暂无")
    lines.extend(["", "**建议保存为 Visual System（整体视觉系统）**"])
    if system_candidates:
        lines.extend(_format_candidate_line(candidate, "Visual System") for candidate in system_candidates)
    else:
        lines.append("- 暂无")
    skipped = suggestions.get("skipped") or []
    if skipped:
        lines.extend(["", "**未自动建议的原因**", *[f"- {item}" for item in skipped]])
    lines.extend(
        [
            "",
            "这些只是候选，不会自动写入长期记忆；确认后再保存。候选记录和 ID 已保留在 reuse_suggestions 中。",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Generation run JSON path, or '-' for stdin.")
    parser.add_argument("--liked", choices=["true", "false"])
    parser.add_argument("--notes")
    parser.add_argument("--attempt", type=int, help="One-based generation attempt number.")
    parser.add_argument("--max-attempts", type=int, help="Maximum attempts planned for this generation request.")
    parser.add_argument("--retry-of", help="Generation run id or logical request id this attempt retries.")
    parser.add_argument("--retryable", choices=["true", "false"], help="Whether the failure should be considered retryable.")
    parser.add_argument(
        "--workspace-mirror",
        action="store_true",
        help=(
            "After archiving, create symlinks under <cwd>/outputs/aether-mirror/<run_id>/ "
            "pointing to each archived output so the workspace has a stable path to "
            "open the latest generated image without copying the bytes."
        ),
    )
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
    if args.workspace_mirror and record.get("outputs"):
        mirror_dir = Path.cwd() / "outputs" / "aether-mirror" / record["id"]
        mirror_dir.mkdir(parents=True, exist_ok=True)
        for index, output in enumerate(record["outputs"], start=1):
            image_path = output.get("image_path") or output.get("asset_path")
            if not image_path:
                continue
            target = mirror_dir / f"image-{index}.png"
            try:
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.symlink(image_path, target)
            except OSError:
                # Fallback to a copy on platforms that forbid symlinks.
                target.write_bytes(Path(image_path).read_bytes())
        record["workspace_mirror"] = str(mirror_dir)
    if args.liked is not None or args.notes:
        feedback = {}
        if args.liked is not None:
            feedback["liked"] = args.liked == "true"
        if args.notes:
            feedback["notes"] = args.notes
        status = "liked" if feedback.get("liked") is True else "rejected" if feedback.get("liked") is False else None
        record = store.update_generation_feedback(record["id"], feedback, status)
    reuse_suggestion_message = build_reuse_suggestion_message(record)
    if reuse_suggestion_message:
        record["reuse_suggestion_message"] = reuse_suggestion_message
    json.dump(record, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
