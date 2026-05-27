from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .assets import ingest_asset
from .config import ensure_configured_dirs, load_config
from .generation_params import apply_generation_skill_params, apply_prompt_generation_params
from .jsonio import dump_json, read_json_arg
from .output_archiving import archive_generation_outputs
from .similarity import compare_profiles, decision_for_score
from .storage import AetherStore
from .validation import validate_payload


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _store() -> tuple[Any, AetherStore]:
    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()
    return config, store


def _ingest_source_references(config: Any, store: AetherStore, payload: dict[str, Any]) -> dict[str, Any]:
    references = payload.get("source_references", [])
    updated_references = []
    for reference in references:
        if not isinstance(reference, dict) or not reference.get("image_path"):
            updated_references.append(reference)
            continue
        image_path = Path(reference["image_path"]).expanduser()
        if not image_path.exists():
            updated_references.append(reference)
            continue
        asset_payload = ingest_asset(config, image_path, "reference")
        asset = store.create_asset(asset_payload)
        updated = {
            **reference,
            "original_image_path": reference["image_path"],
            "image_path": asset["asset_path"],
            "asset_id": asset["id"],
            "sha256": asset["sha256"],
        }
        updated_references.append(updated)
    payload["source_references"] = updated_references
    return payload


def cmd_init(_: argparse.Namespace) -> None:
    config, store = _store()
    dump_json(
        {
            "ok": True,
            "config_path": str(config.path),
            "database_path": str(config.database_path),
            "created_dirs": [str(path) for path in ensure_configured_dirs(config)],
        }
    )


def cmd_config_show(_: argparse.Namespace) -> None:
    config = load_config()
    dump_json({"path": str(config.path), "root": str(config.root), "data": config.data})


def cmd_doctor(_: argparse.Namespace) -> None:
    config, store = _store()
    style_count = len(store.list_styles())
    dump_json(
        {
            "ok": True,
            "config_path": str(config.path),
            "database_path": str(config.database_path),
            "style_count": style_count,
            "product_form": config.data.get("project", {}).get("productForm"),
        }
    )


def cmd_style_create(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    if args.ingest_assets:
        payload = _ingest_source_references(config, store, payload)
    dump_json(store.create_style(payload))


def cmd_style_branch(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    payload["parent_style_id"] = args.parent_style_id
    payload.setdefault("status", "draft")
    if args.ingest_assets:
        payload = _ingest_source_references(config, store, payload)
    dump_json(store.create_style(payload))


def cmd_style_status(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.update_style_status(args.style_id, args.status))


def cmd_style_merge(args: argparse.Namespace) -> None:
    _, store = _store()
    if not store.get_style(args.target_style_id):
        raise SystemExit(f"Target style not found: {args.target_style_id}")
    dump_json(store.update_style_status(args.source_style_id, "merged", merged_into_style_id=args.target_style_id))


def style_summary(style: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": style["id"],
        "name": style["name"],
        "summary": style["summary"],
        "tags": style["tags"],
        "status": style["status"],
        "reference_count": len(style.get("source_references", [])),
        "parent_style_id": style.get("parent_style_id"),
        "merged_into_style_id": style.get("merged_into_style_id"),
        "updated_at": style["updated_at"],
    }


def _display_path(config: Any, image_path: str) -> str:
    path = Path(image_path).expanduser()
    if path.is_absolute():
        return str(path)
    return str(config.resolve_path(path))


def style_description(config: Any, style: dict[str, Any]) -> dict[str, Any]:
    reference_images: list[dict[str, Any]] = []
    for index, reference in enumerate(style.get("source_references", []), start=1):
        if not isinstance(reference, dict):
            continue
        image_path = reference.get("image_path")
        item = {
            "index": index,
            "image_path": image_path,
            "display_path": _display_path(config, image_path) if image_path else None,
            "role": reference.get("role", ""),
            "source_prompt": reference.get("source_prompt", ""),
            "user_note": reference.get("user_note", ""),
            "asset_id": reference.get("asset_id", ""),
            "sha256": reference.get("sha256", ""),
        }
        reference_images.append({key: value for key, value in item.items() if value not in (None, "")})

    return {
        "style": style_summary(style),
        "parameter_definition": {
            "style_profile": style.get("style_profile", {}),
            "prompt_template": style.get("prompt_template", ""),
            "negative_prompt": style.get("negative_prompt", ""),
        },
        "reference_images": reference_images,
    }


def cmd_style_list(args: argparse.Namespace) -> None:
    _, store = _store()
    styles = store.list_styles(status=args.status)
    if args.summary:
        dump_json([style_summary(style) for style in styles])
    else:
        dump_json(styles)


def cmd_style_get(args: argparse.Namespace) -> None:
    _, store = _store()
    style = store.get_style(args.style_id)
    if not style:
        raise SystemExit(f"Style not found: {args.style_id}")
    dump_json(style)


def cmd_style_describe(args: argparse.Namespace) -> None:
    config, store = _store()
    style = store.get_style(args.style_id)
    if not style:
        raise SystemExit(f"Style not found: {args.style_id}")
    dump_json(style_description(config, style))


def cmd_style_compare(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.profile)
    source_profile = payload.get("style_profile", payload)
    style_config = config.data.get("style", {})
    weights = style_config.get("similarityWeights", {})
    thresholds = style_config.get("similarityThresholds", {})

    results: list[dict[str, Any]] = []
    for candidate in store.list_styles(status=args.status):
        comparison = compare_profiles(source_profile, candidate["style_profile"], weights)
        decision = decision_for_score(comparison["similarity_score"], thresholds)
        results.append(
            {
                "candidate_style_id": candidate["id"],
                "candidate_style_name": candidate["name"],
                "similarity_score": comparison["similarity_score"],
                "decision": decision,
                "matched_dimensions": comparison["matched_dimensions"],
                "different_dimensions": comparison["different_dimensions"],
                "dimension_scores": comparison["dimension_scores"],
                "reason": "Deterministic field-weight similarity. Codex should add semantic explanation before final user confirmation.",
            }
        )
    results.sort(key=lambda item: item["similarity_score"], reverse=True)
    dump_json({"results": results[: args.limit]})


def cmd_similarity_save(args: argparse.Namespace) -> None:
    _, store = _store()
    payload = read_json_arg(args.json)
    dump_json(store.save_similarity_result(payload))


def cmd_asset_ingest(args: argparse.Namespace) -> None:
    config, store = _store()
    asset = ingest_asset(config, args.path, args.kind)
    dump_json(store.create_asset(asset))


def cmd_asset_list(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.list_assets(kind=args.kind, limit=args.limit))


def cmd_asset_stats(_: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.asset_stats())


def cmd_asset_duplicates(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.duplicate_assets(kind=args.kind))


def cmd_asset_unreferenced(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.unreferenced_assets(kind=args.kind))


def cmd_prompt_save(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    payload = apply_prompt_generation_params(payload, config)
    dump_json(store.save_prompt_record(payload))


def cmd_prompt_render(args: argparse.Namespace) -> None:
    config, store = _store()
    style = store.get_style(args.style_id)
    if not style:
        raise SystemExit(f"Style not found: {args.style_id}")

    target_generation_skill = args.target_generation_skill or config.data["generation"]["defaultGenerationSkill"]
    style_profile = style["style_profile"]
    template = style["prompt_template"] or "{source_prompt}, {style_summary}, {style_profile}"
    values = SafeFormatDict(
        {
            "source_prompt": args.source_prompt,
            "style_name": style["name"],
            "style_summary": style["summary"],
            "style_profile": ", ".join(f"{key}: {value}" for key, value in style_profile.items() if value),
            "negative_prompt": style["negative_prompt"],
            "target_generation_skill": target_generation_skill,
        }
    )
    try:
        rendered = template.format_map(values)
    except ValueError as exc:
        raise SystemExit(f"Invalid prompt template: {exc}") from exc
    record = {
        "source_prompt": args.source_prompt,
        "style_id": style["id"],
        "target_generation_skill": target_generation_skill,
        "constraints": {},
        "intent_analysis": {},
        "refined_prompt": rendered,
        "negative_prompt": style["negative_prompt"],
        "generation_params": config.data.get("generation", {}).get("defaultParams", {}),
        "variants": [],
        "assumptions": ["Rendered from style prompt_template without Codex semantic refinement."],
    }
    if args.save:
        dump_json(store.save_prompt_record(record))
    else:
        dump_json(record)


def cmd_generation_record(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    payload = apply_generation_skill_params(payload, config)
    payload = archive_generation_outputs(config, store, payload)
    dump_json(store.create_generation_run(payload))


def cmd_generation_feedback(args: argparse.Namespace) -> None:
    _, store = _store()
    feedback: dict[str, Any] = {}
    if args.liked is not None:
        feedback["liked"] = args.liked.lower() == "true"
    if args.notes:
        feedback["notes"] = args.notes
    status = "liked" if feedback.get("liked") is True else "rejected" if feedback.get("liked") is False else None
    dump_json(store.update_generation_feedback(args.run_id, feedback, status))


def _text_preview(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _first_output_path(outputs: list[Any]) -> str:
    if not outputs:
        return ""
    first = outputs[0]
    if isinstance(first, dict):
        return first.get("image_path") or first.get("asset_path") or first.get("path") or first.get("url") or ""
    if isinstance(first, str):
        return first
    return ""


def generation_summary(run: dict[str, Any]) -> dict[str, Any]:
    review = run.get("visual_review", {})
    return {
        "id": run["id"],
        "style_id": run.get("style_id"),
        "status": run.get("status"),
        "generation_skill": run.get("generation_skill"),
        "prompt_preview": _text_preview(run.get("refined_prompt", "")),
        "aspect_ratio": run.get("skill_params", {}).get("aspectRatio"),
        "output_count": len(run.get("outputs", [])),
        "first_output": _first_output_path(run.get("outputs", [])),
        "style_consistency": review.get("style_consistency"),
        "review_score": review.get("score"),
        "recommendation": review.get("recommendation"),
        "liked": run.get("feedback", {}).get("liked"),
        "updated_at": run.get("updated_at"),
    }


def cmd_generation_list(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(
        [
            generation_summary(run)
            for run in store.list_generation_runs(
                style_id=args.style_id,
                status=args.status,
                review=args.review,
                limit=args.limit,
            )
        ]
    )


def cmd_generation_get(args: argparse.Namespace) -> None:
    _, store = _store()
    run = store.get_generation_run(args.run_id)
    if not run:
        raise SystemExit(f"Generation run not found: {args.run_id}")
    dump_json(run)


def cmd_generation_stats(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.generation_stats(style_id=args.style_id))


def cmd_validate(args: argparse.Namespace) -> None:
    payload = read_json_arg(args.json)
    validate_payload(args.kind, payload)
    dump_json({"ok": True, "kind": args.kind})


def cmd_serve(args: argparse.Namespace) -> None:
    config, _ = _store()
    dump_json(
        {
            "ok": False,
            "reason": "The phase-one implementation is CLI-first. A local HTTP service is intentionally deferred.",
            "suggested_command_shape": f"aether serve --host {args.host or config.data['backend']['host']} --port {args.port or config.data['backend']['port']}",
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aether")
    sub = parser.add_subparsers(required=True)

    init = sub.add_parser("init")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=cmd_doctor)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(required=True)
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(func=cmd_config_show)

    style = sub.add_parser("style")
    style_sub = style.add_subparsers(required=True)
    style_create = style_sub.add_parser("create")
    style_create.add_argument("--json", required=True, help="JSON file path, or '-' for stdin.")
    style_create.add_argument("--ingest-assets", action="store_true", help="Copy source_references images into configured asset storage.")
    style_create.set_defaults(func=cmd_style_create)
    style_branch = style_sub.add_parser("branch")
    style_branch.add_argument("parent_style_id")
    style_branch.add_argument("--json", required=True, help="Style card JSON for the branch.")
    style_branch.add_argument("--ingest-assets", action="store_true", help="Copy source_references images into configured asset storage.")
    style_branch.set_defaults(func=cmd_style_branch)
    style_list = style_sub.add_parser("list")
    style_list.add_argument("--status")
    style_list.add_argument("--summary", action="store_true", help="Return compact style catalog rows.")
    style_list.set_defaults(func=cmd_style_list)
    style_get = style_sub.add_parser("get")
    style_get.add_argument("style_id")
    style_get.set_defaults(func=cmd_style_get)
    style_describe = style_sub.add_parser("describe")
    style_describe.add_argument("style_id")
    style_describe.set_defaults(func=cmd_style_describe)
    style_compare = style_sub.add_parser("compare")
    style_compare.add_argument("--profile", required=True, help="Style profile JSON file path, or '-' for stdin.")
    style_compare.add_argument("--status", default="active")
    style_compare.add_argument("--limit", type=int, default=5)
    style_compare.set_defaults(func=cmd_style_compare)
    style_activate = style_sub.add_parser("activate")
    style_activate.add_argument("style_id")
    style_activate.set_defaults(func=cmd_style_status, status="active")
    style_archive = style_sub.add_parser("archive")
    style_archive.add_argument("style_id")
    style_archive.set_defaults(func=cmd_style_status, status="archived")
    style_merge = style_sub.add_parser("merge")
    style_merge.add_argument("source_style_id")
    style_merge.add_argument("target_style_id")
    style_merge.set_defaults(func=cmd_style_merge)

    similarity = sub.add_parser("similarity")
    similarity_sub = similarity.add_subparsers(required=True)
    similarity_save = similarity_sub.add_parser("save")
    similarity_save.add_argument("--json", required=True)
    similarity_save.set_defaults(func=cmd_similarity_save)

    asset = sub.add_parser("asset")
    asset_sub = asset.add_subparsers(required=True)
    asset_ingest = asset_sub.add_parser("ingest")
    asset_ingest.add_argument("--path", required=True)
    asset_ingest.add_argument("--kind", choices=["reference", "generated"], default="reference")
    asset_ingest.set_defaults(func=cmd_asset_ingest)
    asset_list = asset_sub.add_parser("list")
    asset_list.add_argument("--kind", choices=["reference", "generated"])
    asset_list.add_argument("--limit", type=int, default=50)
    asset_list.set_defaults(func=cmd_asset_list)
    asset_stats = asset_sub.add_parser("stats")
    asset_stats.set_defaults(func=cmd_asset_stats)
    asset_duplicates = asset_sub.add_parser("duplicates")
    asset_duplicates.add_argument("--kind", choices=["reference", "generated"])
    asset_duplicates.set_defaults(func=cmd_asset_duplicates)
    asset_unreferenced = asset_sub.add_parser("unreferenced")
    asset_unreferenced.add_argument("--kind", choices=["reference", "generated"])
    asset_unreferenced.set_defaults(func=cmd_asset_unreferenced)

    prompt = sub.add_parser("prompt")
    prompt_sub = prompt.add_subparsers(required=True)
    prompt_save = prompt_sub.add_parser("save")
    prompt_save.add_argument("--json", required=True)
    prompt_save.set_defaults(func=cmd_prompt_save)
    prompt_render = prompt_sub.add_parser("render")
    prompt_render.add_argument("--style-id", required=True)
    prompt_render.add_argument("--source-prompt", required=True)
    prompt_render.add_argument("--target-generation-skill")
    prompt_render.add_argument("--save", action="store_true")
    prompt_render.set_defaults(func=cmd_prompt_render)

    generation = sub.add_parser("generation")
    generation_sub = generation.add_subparsers(required=True)
    generation_record = generation_sub.add_parser("record")
    generation_record.add_argument("--json", required=True)
    generation_record.set_defaults(func=cmd_generation_record)
    generation_list = generation_sub.add_parser("list")
    generation_list.add_argument("--style-id")
    generation_list.add_argument("--status")
    generation_list.add_argument("--review")
    generation_list.add_argument("--limit", type=int, default=20)
    generation_list.set_defaults(func=cmd_generation_list)
    generation_get = generation_sub.add_parser("get")
    generation_get.add_argument("run_id")
    generation_get.set_defaults(func=cmd_generation_get)
    generation_stats = generation_sub.add_parser("stats")
    generation_stats.add_argument("--style-id")
    generation_stats.set_defaults(func=cmd_generation_stats)
    generation_feedback = generation_sub.add_parser("feedback")
    generation_feedback.add_argument("run_id")
    generation_feedback.add_argument("--liked", choices=["true", "false"])
    generation_feedback.add_argument("--notes")
    generation_feedback.set_defaults(func=cmd_generation_feedback)

    serve = sub.add_parser("serve")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=cmd_serve)

    validate = sub.add_parser("validate")
    validate.add_argument("kind", choices=["style", "prompt", "generation"])
    validate.add_argument("--json", required=True)
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
