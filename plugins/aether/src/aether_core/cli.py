from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .assets import ingest_asset
from .composer import compose_prompt
from .config import ensure_configured_dirs, load_config
from .generation_params import apply_generation_skill_params, apply_prompt_generation_params
from .jsonio import dump_json, read_json_arg
from .output_archiving import archive_generation_outputs
from .storage import AetherStore
from .validation import validate_payload


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
    visual_asset_count = len(store.list_visual_assets())
    dump_json(
        {
            "ok": True,
            "config_path": str(config.path),
            "database_path": str(config.database_path),
            "visual_asset_count": visual_asset_count,
            "product_form": config.data.get("project", {}).get("productForm"),
        }
    )


def _display_path(config: Any, image_path: str) -> str:
    path = Path(image_path).expanduser()
    if path.is_absolute():
        return str(path)
    return str(config.resolve_path(path))


def cmd_similarity_save(args: argparse.Namespace) -> None:
    _, store = _store()
    payload = read_json_arg(args.json)
    dump_json(store.save_similarity_result(payload))


def visual_asset_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "type": candidate["type"],
        "name": candidate["name"],
        "reuse_score": candidate["reuse_score"],
        "decision": candidate["decision"],
        "similar_candidate_count": len(candidate.get("similar_candidates", [])),
        "status": candidate["status"],
        "target_asset_id": candidate.get("target_asset_id"),
        "confirmed_asset_id": candidate.get("confirmed_asset_id"),
        "updated_at": candidate["updated_at"],
    }


def visual_asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": asset["id"],
        "type": asset["type"],
        "name": asset["name"],
        "summary": asset["summary"],
        "tags": asset["tags"],
        "status": asset["status"],
        "prompt_fragment_count": len(asset.get("prompt_fragments", [])),
        "negative_fragment_count": len(asset.get("negative_fragments", [])),
        "reference_count": len(asset.get("source_references", [])),
        "updated_at": asset["updated_at"],
    }


def cmd_visual_asset_create(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    if args.ingest_assets:
        payload = _ingest_source_references(config, store, payload)
    dump_json(store.create_visual_asset(payload))


def cmd_visual_asset_branch(args: argparse.Namespace) -> None:
    config, store = _store()
    payload = read_json_arg(args.json)
    if args.ingest_assets:
        payload = _ingest_source_references(config, store, payload)
    dump_json(store.branch_visual_asset(args.parent_asset_id, payload))


def cmd_visual_asset_list(args: argparse.Namespace) -> None:
    _, store = _store()
    assets = store.list_visual_assets(
        asset_type=args.type,
        status=args.status,
        tag=args.tag,
        query=args.query,
        limit=args.limit,
    )
    dump_json([visual_asset_summary(asset) for asset in assets] if args.summary else assets)


def cmd_visual_asset_get(args: argparse.Namespace) -> None:
    _, store = _store()
    asset = store.get_visual_asset(args.asset_id)
    if not asset:
        raise SystemExit(f"Visual asset not found: {args.asset_id}")
    dump_json(asset)


def cmd_visual_asset_status(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.update_visual_asset_status(args.asset_id, args.status))


def cmd_visual_asset_merge(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.merge_visual_asset(args.source_asset_id, args.target_asset_id))


def cmd_visual_asset_candidates_create(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.create_visual_asset_candidate_batch(read_json_arg(args.json)))


def cmd_visual_asset_candidates_list(args: argparse.Namespace) -> None:
    _, store = _store()
    candidates = store.list_visual_asset_candidates(
        status=args.status,
        batch_id=args.batch_id,
        asset_type=args.type,
        limit=args.limit,
    )
    dump_json([visual_asset_candidate_summary(candidate) for candidate in candidates] if args.summary else candidates)


def cmd_visual_asset_candidate_get(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.get_visual_asset_candidate(args.candidate_id)
    if not candidate:
        raise SystemExit(f"Visual asset candidate not found: {args.candidate_id}")
    dump_json(candidate)


def cmd_visual_asset_candidate_decide(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.decide_visual_asset_candidate(args.candidate_id, args.decision, args.target_asset_id))


def cmd_visual_asset_evidence(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(
        store.list_visual_asset_evidence(
            asset_id=args.asset_id,
            evidence_type=args.type,
            limit=args.limit,
        )
    )


def cmd_visual_asset_quality(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.visual_asset_quality(args.asset_id))


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


def cmd_prompt_compose(args: argparse.Namespace) -> None:
    config, store = _store()
    target_generation_skill = args.target_generation_skill or config.data["generation"].get("defaultGenerationSkill")
    record = compose_prompt(
        store,
        args.source_prompt,
        explicit_asset_ids=args.asset_id or [],
        query=args.query or "",
        aspect_ratio=args.aspect_ratio,
        target_generation_skill=target_generation_skill,
        default_generation_params=config.data.get("generation", {}).get("defaultParams", {}),
    )
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
        "mode": run.get("mode", "generate"),
        "source_generation_id": run.get("source_generation_id"),
        "source_output_asset_id": run.get("source_output_asset_id"),
        "selected_assets": run.get("selected_assets", []),
        "status": run.get("status"),
        "generation_skill": run.get("generation_skill"),
        "prompt_preview": _text_preview(run.get("refined_prompt", "")),
        "edit_instruction_preview": _text_preview(run.get("edit_instruction", "")),
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
                asset_id=args.asset_id,
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
    dump_json(store.generation_stats(asset_id=args.asset_id))


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

    similarity = sub.add_parser("similarity")
    similarity_sub = similarity.add_subparsers(required=True)
    similarity_save = similarity_sub.add_parser("save")
    similarity_save.add_argument("--json", required=True)
    similarity_save.set_defaults(func=cmd_similarity_save)

    visual_asset = sub.add_parser("visual-asset")
    visual_asset_sub = visual_asset.add_subparsers(required=True)
    visual_asset_create = visual_asset_sub.add_parser("create")
    visual_asset_create.add_argument("--json", required=True)
    visual_asset_create.add_argument("--ingest-assets", action="store_true")
    visual_asset_create.set_defaults(func=cmd_visual_asset_create)
    visual_asset_branch = visual_asset_sub.add_parser("branch")
    visual_asset_branch.add_argument("parent_asset_id")
    visual_asset_branch.add_argument("--json", required=True)
    visual_asset_branch.add_argument("--ingest-assets", action="store_true")
    visual_asset_branch.set_defaults(func=cmd_visual_asset_branch)
    visual_asset_list = visual_asset_sub.add_parser("list")
    visual_asset_list.add_argument("--type")
    visual_asset_list.add_argument("--status")
    visual_asset_list.add_argument("--tag")
    visual_asset_list.add_argument("--query")
    visual_asset_list.add_argument("--limit", type=int, default=50)
    visual_asset_list.add_argument("--summary", action="store_true")
    visual_asset_list.set_defaults(func=cmd_visual_asset_list)
    visual_asset_get = visual_asset_sub.add_parser("get")
    visual_asset_get.add_argument("asset_id")
    visual_asset_get.set_defaults(func=cmd_visual_asset_get)
    visual_asset_activate = visual_asset_sub.add_parser("activate")
    visual_asset_activate.add_argument("asset_id")
    visual_asset_activate.set_defaults(func=cmd_visual_asset_status, status="active")
    visual_asset_archive = visual_asset_sub.add_parser("archive")
    visual_asset_archive.add_argument("asset_id")
    visual_asset_archive.set_defaults(func=cmd_visual_asset_status, status="archived")
    visual_asset_merge = visual_asset_sub.add_parser("merge")
    visual_asset_merge.add_argument("source_asset_id")
    visual_asset_merge.add_argument("target_asset_id")
    visual_asset_merge.set_defaults(func=cmd_visual_asset_merge)
    visual_asset_candidates = visual_asset_sub.add_parser("candidates")
    visual_asset_candidates_sub = visual_asset_candidates.add_subparsers(required=True)
    visual_asset_candidates_create = visual_asset_candidates_sub.add_parser("create")
    visual_asset_candidates_create.add_argument("--json", required=True)
    visual_asset_candidates_create.set_defaults(func=cmd_visual_asset_candidates_create)
    visual_asset_candidates_list = visual_asset_candidates_sub.add_parser("list")
    visual_asset_candidates_list.add_argument("--status")
    visual_asset_candidates_list.add_argument("--batch-id")
    visual_asset_candidates_list.add_argument("--type")
    visual_asset_candidates_list.add_argument("--limit", type=int, default=50)
    visual_asset_candidates_list.add_argument("--summary", action="store_true")
    visual_asset_candidates_list.set_defaults(func=cmd_visual_asset_candidates_list)
    visual_asset_candidate_get = visual_asset_candidates_sub.add_parser("get")
    visual_asset_candidate_get.add_argument("candidate_id")
    visual_asset_candidate_get.set_defaults(func=cmd_visual_asset_candidate_get)
    visual_asset_candidate_decide = visual_asset_candidates_sub.add_parser("decide")
    visual_asset_candidate_decide.add_argument("candidate_id")
    visual_asset_candidate_decide.add_argument("decision", choices=["existing_asset", "asset_variant", "new_asset", "ignore"])
    visual_asset_candidate_decide.add_argument("--target-asset-id")
    visual_asset_candidate_decide.set_defaults(func=cmd_visual_asset_candidate_decide)
    visual_asset_evidence = visual_asset_sub.add_parser("evidence")
    visual_asset_evidence.add_argument("asset_id")
    visual_asset_evidence.add_argument("--type")
    visual_asset_evidence.add_argument("--limit", type=int, default=50)
    visual_asset_evidence.set_defaults(func=cmd_visual_asset_evidence)
    visual_asset_quality = visual_asset_sub.add_parser("quality")
    visual_asset_quality.add_argument("asset_id")
    visual_asset_quality.set_defaults(func=cmd_visual_asset_quality)

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
    prompt_compose = prompt_sub.add_parser("compose")
    prompt_compose.add_argument("--source-prompt", required=True)
    prompt_compose.add_argument("--asset-id", action="append")
    prompt_compose.add_argument("--query")
    prompt_compose.add_argument("--aspect-ratio")
    prompt_compose.add_argument("--target-generation-skill")
    prompt_compose.add_argument("--save", action="store_true")
    prompt_compose.set_defaults(func=cmd_prompt_compose)

    generation = sub.add_parser("generation")
    generation_sub = generation.add_subparsers(required=True)
    generation_record = generation_sub.add_parser("record")
    generation_record.add_argument("--json", required=True)
    generation_record.set_defaults(func=cmd_generation_record)
    generation_list = generation_sub.add_parser("list")
    generation_list.add_argument("--asset-id")
    generation_list.add_argument("--status")
    generation_list.add_argument("--review")
    generation_list.add_argument("--limit", type=int, default=20)
    generation_list.set_defaults(func=cmd_generation_list)
    generation_get = generation_sub.add_parser("get")
    generation_get.add_argument("run_id")
    generation_get.set_defaults(func=cmd_generation_get)
    generation_stats = generation_sub.add_parser("stats")
    generation_stats.add_argument("--asset-id")
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
    validate.add_argument("kind", choices=["visual-asset", "visual-asset-candidate", "prompt", "generation"])
    validate.add_argument("--json", required=True)
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
