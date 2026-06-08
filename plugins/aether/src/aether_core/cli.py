from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .assets import ingest_asset
from .chat_attachments import (
    chat_reference_name,
    find_input_images_by_indices,
    find_recent_input_images,
    ingest_chat_attachment,
    is_unresolved_chat_reference,
)
from .composer import compose_prompt
from .config import ensure_configured_dirs, load_config
from .generation_params import apply_generation_skill_params, apply_prompt_generation_params
from .jsonio import dump_json, read_json_arg
from .output_archiving import archive_generation_outputs
from .panel import run_panel
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
    unresolved_chat_references = [
        (index, reference) for index, reference in enumerate(references) if is_unresolved_chat_reference(reference)
    ]
    chat_images: dict[int, dict[str, Any]] = {}
    if unresolved_chat_references:
        try:
            explicit_indices = [
                reference.get("input_image_index")
                for _, reference in unresolved_chat_references
                if isinstance(reference.get("input_image_index"), int)
            ]
            if explicit_indices and len(explicit_indices) != len(unresolved_chat_references):
                raise ValueError("Either provide input_image_index for every chat_attachment reference or for none.")
            images = (
                find_input_images_by_indices(explicit_indices)
                if explicit_indices
                else find_recent_input_images(len(unresolved_chat_references))
            )
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(
                "Could not resolve chat_attachment source reference(s). "
                "Pass source_references[].image_path or ensure the current Codex session contains "
                f"at least {len(unresolved_chat_references)} input_image attachment(s). {exc}"
            ) from exc
        chat_images = {index: images[position] for position, (index, _) in enumerate(unresolved_chat_references)}

    updated_references = []
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            updated_references.append(reference)
            continue
        if is_unresolved_chat_reference(reference):
            result = ingest_chat_attachment(
                config,
                store,
                chat_images[index]["image_url"],
                chat_reference_name(reference, index),
                "reference",
            )
            asset = result["asset"]
            updated_references.append(
                {
                    **reference,
                    "image_path": asset["asset_path"],
                    "asset_id": asset["id"],
                    "sha256": asset["sha256"],
                    "mime_type": asset.get("mime_type", result["mime_type"]),
                    "size_bytes": asset.get("size_bytes", 0),
                }
            )
            continue
        if not reference.get("image_path"):
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


def cmd_embedding_status(_: argparse.Namespace) -> None:
    config, store = _store()
    dump_json(store.embedding_status(config.data))


def cmd_embedding_index(args: argparse.Namespace) -> None:
    config, store = _store()
    if args.all and args.entity_type:
        raise SystemExit("--all cannot be combined with --entity-type")
    dump_json(store.index_embeddings(config.data, entity_type=None if args.all else args.entity_type, rebuild=False))


def cmd_embedding_rebuild(args: argparse.Namespace) -> None:
    config, store = _store()
    if args.all and args.entity_type:
        raise SystemExit("--all cannot be combined with --entity-type")
    dump_json(store.index_embeddings(config.data, entity_type=None if args.all else args.entity_type, rebuild=True))


def cmd_recall(args: argparse.Namespace) -> None:
    config, store = _store()
    entity_type = None if args.entity_type == "all" else args.entity_type
    if entity_type:
        dump_json(
            store.hybrid_recall(
                entity_type,
                args.query,
                config=config.data,
                limit=args.limit,
                status=args.status,
                include_unavailable=args.include_unavailable,
            )
        )
        return
    dump_json(
        {
            current_type: store.hybrid_recall(
                current_type,
                args.query,
                config=config.data,
                limit=args.limit,
                status=args.status,
                include_unavailable=args.include_unavailable,
            )
            for current_type in ("visual_asset", "visual_system", "recipe")
        }
    )


def visual_asset_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    suggestion = payload.get("evolution_suggestion", {})
    action = payload.get("evolution_action") or suggestion.get("action")
    target_id = suggestion.get("target_id")
    if not target_id and action in {"attach_evidence", "inherit_variant", "merge_existing"}:
        target_id = candidate.get("target_asset_id")
    target_name = None
    if target_id:
        target_name = next(
            (
                item.get("name")
                for item in candidate.get("similar_candidates", [])
                if item.get("asset_id") == target_id
            ),
            None,
        )
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "type": candidate["type"],
        "name": candidate["name"],
        "dedupe_score": candidate["reuse_score"],
        "evolution_action": action,
        "target_id": target_id,
        "target_name": target_name,
        "similar_candidate_count": len(candidate.get("similar_candidates", [])),
        "status": candidate["status"],
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
        "parent_asset_id": asset.get("parent_asset_id"),
        "merged_into_asset_id": asset.get("merged_into_asset_id"),
        "prompt_fragment_count": len(asset.get("prompt_fragments", [])),
        "negative_fragment_count": len(asset.get("negative_fragments", [])),
        "reference_count": len(asset.get("source_references", [])),
        "updated_at": asset["updated_at"],
    }


def visual_system_summary(system: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": system["id"],
        "kind": system["kind"],
        "name": system["name"],
        "summary": system["summary"],
        "tags": system.get("tags", []),
        "status": system["status"],
        "parent_system_id": system.get("parent_system_id"),
        "merged_into_system_id": system.get("merged_into_system_id"),
        "source_reference_count": len(system.get("source_reference_ids", [])),
        "updated_at": system["updated_at"],
    }


def recipe_summary(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "summary": recipe["summary"],
        "parent_system_ids": recipe.get("parent_system_ids", []),
        "use_cases": recipe.get("use_cases", []),
        "required_asset_types": recipe.get("required_asset_types", []),
        "composition_rule_count": len(recipe.get("composition_rules", [])),
        "recommended_aspect_ratios": recipe.get("recommended_aspect_ratios", []),
        "confidence": recipe.get("confidence"),
        "source": recipe.get("source"),
        "status": recipe["status"],
        "parent_recipe_id": recipe.get("parent_recipe_id"),
        "merged_into_recipe_id": recipe.get("merged_into_recipe_id"),
        "updated_at": recipe["updated_at"],
    }


def candidate_payload_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    metadata = payload.get("metadata", {})
    target_id = metadata.get("target_system_id") or metadata.get("target_recipe_id")
    target_name = None
    for field, id_key in (
        ("related_existing_systems", "system_id"),
        ("related_existing_recipes", "recipe_id"),
    ):
        target_name = next(
            (
                item.get("name")
                for item in payload.get(field, [])
                if item.get(id_key) == target_id
            ),
            None,
        )
        if target_name:
            break
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "name": payload.get("name"),
        "status": candidate["status"],
        "recommendation": metadata.get("recommendation"),
        "evolution_action": metadata.get("evolution_action"),
        "target_id": target_id,
        "target_name": target_name,
        "dedupe_score": metadata.get("dedupe_score"),
        "updated_at": candidate["updated_at"],
    }


def evidence_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    payload = evidence.get("payload", {})
    output = payload.get("output") if isinstance(payload, dict) else None
    review = payload if isinstance(payload, dict) and evidence.get("evidence_type") == "review" else {}
    return {
        "id": evidence["id"],
        "evidence_type": evidence.get("evidence_type"),
        "asset_id": evidence.get("asset_id"),
        "recipe_id": evidence.get("recipe_id"),
        "system_id": evidence.get("system_id"),
        "generation_run_id": evidence.get("generation_run_id") or evidence.get("source_generation_id"),
        "source_candidate_id": evidence.get("source_candidate_id"),
        "source_reference_id": evidence.get("source_reference_id"),
        "output": _first_output_path([output]) if output else "",
        "review": review.get("style_consistency"),
        "score": review.get("score"),
        "recommendation": review.get("recommendation"),
        "created_at": evidence.get("created_at"),
    }


def revision_summary(revision: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": revision["id"],
        "entity_type": revision.get("entity_type"),
        "entity_id": revision.get("entity_id"),
        "action": revision.get("action"),
        "source_candidate_id": revision.get("source_candidate_id"),
        "source_generation_id": revision.get("source_generation_id"),
        "target_entity_id": revision.get("target_entity_id"),
        "changed_fields": sorted((revision.get("diff") or {}).keys()),
        "reason": _text_preview(revision.get("reason", ""), limit=160),
        "created_at": revision.get("created_at"),
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


def cmd_visual_asset_merge_preview(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.visual_asset_merge_preview(args.source_asset_id, args.target_asset_id))


def cmd_visual_asset_candidates_create(args: argparse.Namespace) -> None:
    config, store = _store()
    dump_json(store.create_visual_asset_candidate_batch(read_json_arg(args.json), config=config.data))


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
    candidate = store.decide_visual_asset_candidate(args.candidate_id, args.action, args.target_asset_id)
    if getattr(args, "cleanup", False):
        if args.action != "ignore":
            raise SystemExit("--cleanup is only supported when action is ignore")
        dump_json({"ignored": candidate, "deleted": store.delete_visual_asset_candidate(args.candidate_id)})
        return
    dump_json(candidate)


def cmd_visual_asset_candidate_ignore(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.ignore_visual_asset_candidate(args.candidate_id)
    if args.cleanup:
        dump_json({"ignored": candidate, "deleted": store.delete_visual_asset_candidate(args.candidate_id)})
        return
    dump_json(candidate)


def cmd_visual_asset_candidate_delete(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.delete_visual_asset_candidate(args.candidate_id))


def cmd_visual_asset_candidates_cleanup(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.cleanup_visual_asset_candidates(status=args.status, batch_id=args.batch_id))


def cmd_visual_asset_candidates_compact(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.compact_visual_asset_candidates(status=args.status, batch_id=args.batch_id))


def cmd_visual_asset_candidates_confirm_batch(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.confirm_visual_asset_candidate_batch(args.batch_id))


def cmd_visual_asset_evidence(args: argparse.Namespace) -> None:
    _, store = _store()
    evidence = store.list_visual_asset_evidence(
        asset_id=args.asset_id,
        evidence_type=args.type,
        limit=args.limit,
    )
    dump_json([evidence_summary(item) for item in evidence] if args.summary else evidence)


def cmd_visual_asset_revisions(args: argparse.Namespace) -> None:
    _, store = _store()
    revisions = store.list_revisions("visual_asset", entity_id=args.asset_id, limit=args.limit)
    dump_json([revision_summary(item) for item in revisions] if args.summary else revisions)


def cmd_visual_asset_quality(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.visual_asset_quality(args.asset_id))


def cmd_visual_system_create(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.create_visual_system(read_json_arg(args.json)))


def cmd_visual_system_list(args: argparse.Namespace) -> None:
    _, store = _store()
    systems = store.list_visual_systems(
        kind=args.kind,
        status=args.status,
        query=args.query,
        limit=args.limit,
    )
    dump_json([visual_system_summary(system) for system in systems] if args.summary else systems)


def cmd_visual_system_get(args: argparse.Namespace) -> None:
    _, store = _store()
    system = store.get_visual_system(args.system_id)
    if not system:
        raise SystemExit(f"Visual system not found: {args.system_id}")
    dump_json(system)


def cmd_visual_system_add_asset(args: argparse.Namespace) -> None:
    _, store = _store()
    payload = {
        "asset_id": args.asset_id,
        "role": args.role,
        "weight": args.weight,
        "reason": args.reason or "",
    }
    dump_json(store.set_visual_system_asset(args.system_id, payload))


def cmd_visual_system_merge_preview(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.visual_system_merge_preview(args.source_system_id, args.target_system_id))


def cmd_visual_system_merge(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.merge_visual_system(args.source_system_id, args.target_system_id))


def cmd_visual_system_evidence(args: argparse.Namespace) -> None:
    _, store = _store()
    evidence = store.list_visual_system_evidence(system_id=args.system_id, evidence_type=args.type, limit=args.limit)
    dump_json([evidence_summary(item) for item in evidence] if args.summary else evidence)


def cmd_visual_system_revisions(args: argparse.Namespace) -> None:
    _, store = _store()
    revisions = store.list_revisions("visual_system", entity_id=args.system_id, limit=args.limit)
    dump_json([revision_summary(item) for item in revisions] if args.summary else revisions)


def cmd_visual_system_candidates_list(args: argparse.Namespace) -> None:
    _, store = _store()
    candidates = store.list_visual_system_candidates(batch_id=args.batch_id, status=args.status, limit=args.limit)
    dump_json([candidate_payload_summary(candidate) for candidate in candidates] if args.summary else candidates)


def cmd_visual_system_candidate_get(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.get_visual_system_candidate(args.candidate_id)
    if not candidate:
        raise SystemExit(f"Visual system candidate not found: {args.candidate_id}")
    dump_json(candidate)


def cmd_visual_system_candidate_confirm(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(
        store.confirm_visual_system_candidate(
            args.candidate_id,
            target_system_id=args.target_system_id,
            action=args.action,
            force_new=args.force_new,
        )
    )


def cmd_visual_system_candidate_ignore(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.ignore_visual_system_candidate(args.candidate_id)
    if args.cleanup:
        dump_json({"ignored": candidate, "deleted": store.delete_visual_system_candidate(args.candidate_id)})
        return
    dump_json(candidate)


def cmd_visual_system_candidate_delete(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.delete_visual_system_candidate(args.candidate_id))


def cmd_visual_system_candidates_cleanup(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.cleanup_visual_system_candidates(status=args.status, batch_id=args.batch_id))


def cmd_visual_system_candidates_compact(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.compact_visual_system_candidates(status=args.status, batch_id=args.batch_id))


def cmd_recipe_create(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.create_recipe(read_json_arg(args.json)))


def cmd_recipe_list(args: argparse.Namespace) -> None:
    _, store = _store()
    recipes = store.list_recipes(
        system_id=args.system_id,
        status=args.status,
        query=args.query,
        limit=args.limit,
    )
    dump_json([recipe_summary(recipe) for recipe in recipes] if args.summary else recipes)


def cmd_recipe_get(args: argparse.Namespace) -> None:
    _, store = _store()
    recipe = store.get_recipe(args.recipe_id)
    if not recipe:
        raise SystemExit(f"Recipe not found: {args.recipe_id}")
    dump_json(recipe)


def cmd_recipe_add_asset(args: argparse.Namespace) -> None:
    _, store = _store()
    payload = {
        "asset_id": args.asset_id,
        "role": args.role,
        "weight": args.weight,
        "reason": args.reason or "",
    }
    dump_json(store.set_recipe_asset(args.recipe_id, payload))


def cmd_recipe_merge_preview(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.recipe_merge_preview(args.source_recipe_id, args.target_recipe_id))


def cmd_recipe_merge(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.merge_recipe(args.source_recipe_id, args.target_recipe_id))


def cmd_recipe_evidence(args: argparse.Namespace) -> None:
    _, store = _store()
    evidence = store.list_recipe_evidence(recipe_id=args.recipe_id, evidence_type=args.type, limit=args.limit)
    dump_json([evidence_summary(item) for item in evidence] if args.summary else evidence)


def cmd_recipe_revisions(args: argparse.Namespace) -> None:
    _, store = _store()
    revisions = store.list_revisions("recipe", entity_id=args.recipe_id, limit=args.limit)
    dump_json([revision_summary(item) for item in revisions] if args.summary else revisions)


def cmd_recipe_candidates_list(args: argparse.Namespace) -> None:
    _, store = _store()
    candidates = store.list_recipe_candidates(batch_id=args.batch_id, status=args.status, limit=args.limit)
    dump_json([candidate_payload_summary(candidate) for candidate in candidates] if args.summary else candidates)


def cmd_recipe_candidate_get(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.get_recipe_candidate(args.candidate_id)
    if not candidate:
        raise SystemExit(f"Recipe candidate not found: {args.candidate_id}")
    dump_json(candidate)


def cmd_recipe_candidate_confirm(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(
        store.confirm_recipe_candidate(
            args.candidate_id,
            parent_system_ids=args.system_id,
            target_recipe_id=args.target_recipe_id,
            variant_of_recipe_id=args.variant_of,
            action=args.action,
            force_new=args.force_new,
        )
    )


def cmd_recipe_candidate_ignore(args: argparse.Namespace) -> None:
    _, store = _store()
    candidate = store.ignore_recipe_candidate(args.candidate_id)
    if args.cleanup:
        dump_json({"ignored": candidate, "deleted": store.delete_recipe_candidate(args.candidate_id)})
        return
    dump_json(candidate)


def cmd_recipe_candidate_delete(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.delete_recipe_candidate(args.candidate_id))


def cmd_recipe_candidates_cleanup(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.cleanup_recipe_candidates(status=args.status, batch_id=args.batch_id))


def cmd_recipe_candidates_compact(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.compact_recipe_candidates(status=args.status, batch_id=args.batch_id))


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
        system_ids=args.system_id or [],
        recipe_ids=args.recipe_id or [],
        query=args.query or "",
        aspect_ratio=args.aspect_ratio,
        target_generation_skill=target_generation_skill,
        default_generation_params=config.data.get("generation", {}).get("defaultParams", {}),
        config=config.data,
        include_debug_recall=args.debug_recall,
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
    dump_json(generation_summary(run) if args.summary else run)


def cmd_generation_stats(args: argparse.Namespace) -> None:
    _, store = _store()
    dump_json(store.generation_stats(asset_id=args.asset_id))


def cmd_generation_suggest(args: argparse.Namespace) -> None:
    config, store = _store()
    dump_json(store.suggest_generation_reuse(args.run_id, kind=args.kind, auto=args.auto, config=config.data))


def cmd_validate(args: argparse.Namespace) -> None:
    payload = read_json_arg(args.json)
    validate_payload(args.kind, payload)
    dump_json({"ok": True, "kind": args.kind})


def cmd_serve(args: argparse.Namespace) -> None:
    cmd_panel(args)


def cmd_panel(args: argparse.Namespace) -> None:
    config, store = _store()
    backend = config.data.get("backend", {})
    host = args.host or backend.get("host") or "127.0.0.1"
    port = args.port if args.port is not None else int(backend.get("port") or 3850)
    run_panel(config, store, host=host, port=port, open_browser=args.open)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aether",
        description="Aether local CLI for Codex visual memory, prompt refinement, and generation history.",
        epilog=(
            "Most users can work through Codex natural language. Use this CLI for health checks, "
            "scripting, and inspecting local records."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(required=True, title="commands")

    init = sub.add_parser("init", help="Initialize local Aether storage directories and database.")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser(
        "doctor",
        help="Check the active Aether config, database, and basic local state.",
        description="Check that Aether can load config, initialize storage, and read the visual memory database.",
    )
    doctor.set_defaults(func=cmd_doctor)

    config = sub.add_parser("config", help="Inspect the active Aether configuration.")
    config_sub = config.add_subparsers(required=True)
    config_show = config_sub.add_parser(
        "show",
        help="Print the active config path, root, and config values.",
        description=(
            "Show which config file Aether is using. This is useful when global config, workspace config, "
            "and .aether/config.json could all exist."
        ),
    )
    config_show.set_defaults(func=cmd_config_show)

    embedding = sub.add_parser("embedding", help="Index or inspect optional embedding recall state.")
    embedding_sub = embedding.add_subparsers(required=True)
    embedding_status = embedding_sub.add_parser("status")
    embedding_status.set_defaults(func=cmd_embedding_status)
    embedding_index = embedding_sub.add_parser("index")
    embedding_index.add_argument("--entity-type", choices=["visual_asset", "visual_system", "recipe"])
    embedding_index.add_argument("--all", action="store_true")
    embedding_index.set_defaults(func=cmd_embedding_index)
    embedding_rebuild = embedding_sub.add_parser("rebuild")
    embedding_rebuild.add_argument("--entity-type", choices=["visual_asset", "visual_system", "recipe"])
    embedding_rebuild.add_argument("--all", action="store_true")
    embedding_rebuild.set_defaults(func=cmd_embedding_rebuild)

    recall = sub.add_parser("recall", help="Search visual memory with lexical and optional embedding recall.")
    recall.add_argument("entity_type", choices=["visual_asset", "visual_system", "recipe", "all"])
    recall.add_argument("--query", required=True)
    recall.add_argument("--status", choices=["active"], default="active", help="Recall only active visual memory by default.")
    recall.add_argument(
        "--include-unavailable",
        action="store_true",
        help="Admin/debug mode: include archived, deprecated, merged, and merged-into records in recall results.",
    )
    recall.add_argument("--limit", type=int, default=5)
    recall.set_defaults(func=cmd_recall)

    visual_asset = sub.add_parser(
        "visual-asset",
        help="List, inspect, and maintain reusable visual memories.",
        description=(
            "Reusable visual memories include styles, lighting, color palettes, compositions, moods, "
            "characters, scenes, props, and negative rule sets."
        ),
    )
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
    visual_asset_list = visual_asset_sub.add_parser(
        "list",
        help="List saved visual memories.",
        description="List saved visual memories with optional filters for type, status, tag, and query.",
    )
    visual_asset_list.add_argument("--type", help="Filter by visual memory type, such as style or lighting.")
    visual_asset_list.add_argument("--status", help="Filter by status, such as active or archived.")
    visual_asset_list.add_argument("--tag", help="Filter by tag.")
    visual_asset_list.add_argument("--query", help="Search names, summaries, and reusable prompt fragments.")
    visual_asset_list.add_argument("--limit", type=int, default=50, help="Maximum records to return.")
    visual_asset_list.add_argument("--summary", action="store_true", help="Return compact summaries instead of full records.")
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
    visual_asset_merge_preview = visual_asset_sub.add_parser("merge-preview")
    visual_asset_merge_preview.add_argument("source_asset_id")
    visual_asset_merge_preview.add_argument("target_asset_id")
    visual_asset_merge_preview.set_defaults(func=cmd_visual_asset_merge_preview)
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
    visual_asset_candidate_decide.add_argument(
        "action",
        choices=[
            "attach_evidence",
            "create_new",
            "inherit_variant",
            "merge_existing",
            "ignore",
        ],
    )
    visual_asset_candidate_decide.add_argument("--target-asset-id")
    visual_asset_candidate_decide.add_argument("--cleanup", action="store_true")
    visual_asset_candidate_decide.set_defaults(func=cmd_visual_asset_candidate_decide)
    visual_asset_candidate_ignore = visual_asset_candidates_sub.add_parser("ignore")
    visual_asset_candidate_ignore.add_argument("candidate_id")
    visual_asset_candidate_ignore.add_argument("--cleanup", action="store_true")
    visual_asset_candidate_ignore.set_defaults(func=cmd_visual_asset_candidate_ignore)
    visual_asset_candidate_delete = visual_asset_candidates_sub.add_parser("delete")
    visual_asset_candidate_delete.add_argument("candidate_id")
    visual_asset_candidate_delete.set_defaults(func=cmd_visual_asset_candidate_delete)
    visual_asset_candidates_cleanup = visual_asset_candidates_sub.add_parser("cleanup")
    visual_asset_candidates_cleanup.add_argument("--status", choices=["ignored"], default="ignored")
    visual_asset_candidates_cleanup.add_argument("--batch-id")
    visual_asset_candidates_cleanup.set_defaults(func=cmd_visual_asset_candidates_cleanup)
    visual_asset_candidates_compact = visual_asset_candidates_sub.add_parser("compact")
    visual_asset_candidates_compact.add_argument("--status", choices=["pending", "confirmed", "ignored"])
    visual_asset_candidates_compact.add_argument("--batch-id")
    visual_asset_candidates_compact.set_defaults(func=cmd_visual_asset_candidates_compact)
    visual_asset_candidates_confirm_batch = visual_asset_candidates_sub.add_parser("confirm-batch")
    visual_asset_candidates_confirm_batch.add_argument("batch_id")
    visual_asset_candidates_confirm_batch.set_defaults(func=cmd_visual_asset_candidates_confirm_batch)
    visual_asset_evidence = visual_asset_sub.add_parser("evidence")
    visual_asset_evidence.add_argument("asset_id")
    visual_asset_evidence.add_argument("--type")
    visual_asset_evidence.add_argument("--limit", type=int, default=50)
    visual_asset_evidence.add_argument("--summary", action="store_true")
    visual_asset_evidence.set_defaults(func=cmd_visual_asset_evidence)
    visual_asset_revisions = visual_asset_sub.add_parser("revisions")
    visual_asset_revisions.add_argument("asset_id")
    visual_asset_revisions.add_argument("--limit", type=int, default=50)
    visual_asset_revisions.add_argument("--summary", action="store_true")
    visual_asset_revisions.set_defaults(func=cmd_visual_asset_revisions)
    visual_asset_quality = visual_asset_sub.add_parser("quality")
    visual_asset_quality.add_argument("asset_id")
    visual_asset_quality.set_defaults(func=cmd_visual_asset_quality)

    visual_system = sub.add_parser("visual-system", help="Manage higher-level visual systems and art directions.")
    visual_system_sub = visual_system.add_subparsers(required=True)
    visual_system_create = visual_system_sub.add_parser("create")
    visual_system_create.add_argument("--json", required=True)
    visual_system_create.set_defaults(func=cmd_visual_system_create)
    visual_system_list = visual_system_sub.add_parser("list")
    visual_system_list.add_argument("--kind", choices=["worldview", "genre", "series", "art_direction"])
    visual_system_list.add_argument("--status")
    visual_system_list.add_argument("--query")
    visual_system_list.add_argument("--limit", type=int, default=50)
    visual_system_list.add_argument("--summary", action="store_true")
    visual_system_list.set_defaults(func=cmd_visual_system_list)
    visual_system_get = visual_system_sub.add_parser("get")
    visual_system_get.add_argument("system_id")
    visual_system_get.set_defaults(func=cmd_visual_system_get)
    visual_system_add_asset = visual_system_sub.add_parser("add-asset")
    visual_system_add_asset.add_argument("system_id")
    visual_system_add_asset.add_argument("asset_id")
    visual_system_add_asset.add_argument("--role", choices=["core", "optional", "avoid", "reference_only"], default="optional")
    visual_system_add_asset.add_argument("--weight", type=float, default=0.5)
    visual_system_add_asset.add_argument("--reason")
    visual_system_add_asset.set_defaults(func=cmd_visual_system_add_asset)
    visual_system_merge_preview = visual_system_sub.add_parser("merge-preview")
    visual_system_merge_preview.add_argument("source_system_id")
    visual_system_merge_preview.add_argument("target_system_id")
    visual_system_merge_preview.set_defaults(func=cmd_visual_system_merge_preview)
    visual_system_merge = visual_system_sub.add_parser("merge")
    visual_system_merge.add_argument("source_system_id")
    visual_system_merge.add_argument("target_system_id")
    visual_system_merge.set_defaults(func=cmd_visual_system_merge)
    visual_system_evidence = visual_system_sub.add_parser("evidence")
    visual_system_evidence.add_argument("system_id")
    visual_system_evidence.add_argument("--type")
    visual_system_evidence.add_argument("--limit", type=int, default=50)
    visual_system_evidence.add_argument("--summary", action="store_true")
    visual_system_evidence.set_defaults(func=cmd_visual_system_evidence)
    visual_system_revisions = visual_system_sub.add_parser("revisions")
    visual_system_revisions.add_argument("system_id")
    visual_system_revisions.add_argument("--limit", type=int, default=50)
    visual_system_revisions.add_argument("--summary", action="store_true")
    visual_system_revisions.set_defaults(func=cmd_visual_system_revisions)
    visual_system_candidates = visual_system_sub.add_parser("candidates")
    visual_system_candidates_sub = visual_system_candidates.add_subparsers(required=True)
    visual_system_candidates_list = visual_system_candidates_sub.add_parser("list")
    visual_system_candidates_list.add_argument("--batch-id")
    visual_system_candidates_list.add_argument("--status")
    visual_system_candidates_list.add_argument("--limit", type=int, default=50)
    visual_system_candidates_list.add_argument("--summary", action="store_true")
    visual_system_candidates_list.set_defaults(func=cmd_visual_system_candidates_list)
    visual_system_candidate_get = visual_system_candidates_sub.add_parser("get")
    visual_system_candidate_get.add_argument("candidate_id")
    visual_system_candidate_get.set_defaults(func=cmd_visual_system_candidate_get)
    visual_system_candidate_confirm = visual_system_candidates_sub.add_parser("confirm")
    visual_system_candidate_confirm.add_argument("candidate_id")
    visual_system_candidate_confirm.add_argument("--target-system-id")
    visual_system_candidate_confirm.add_argument(
        "--action",
        choices=["attach_evidence", "create_new", "inherit_variant", "merge_existing"],
    )
    visual_system_candidate_confirm.add_argument("--force-new", action="store_true")
    visual_system_candidate_confirm.set_defaults(func=cmd_visual_system_candidate_confirm)
    visual_system_candidate_ignore = visual_system_candidates_sub.add_parser("ignore")
    visual_system_candidate_ignore.add_argument("candidate_id")
    visual_system_candidate_ignore.add_argument("--cleanup", action="store_true")
    visual_system_candidate_ignore.set_defaults(func=cmd_visual_system_candidate_ignore)
    visual_system_candidate_delete = visual_system_candidates_sub.add_parser("delete")
    visual_system_candidate_delete.add_argument("candidate_id")
    visual_system_candidate_delete.set_defaults(func=cmd_visual_system_candidate_delete)
    visual_system_candidates_cleanup = visual_system_candidates_sub.add_parser("cleanup")
    visual_system_candidates_cleanup.add_argument("--status", choices=["ignored"], default="ignored")
    visual_system_candidates_cleanup.add_argument("--batch-id")
    visual_system_candidates_cleanup.set_defaults(func=cmd_visual_system_candidates_cleanup)
    visual_system_candidates_compact = visual_system_candidates_sub.add_parser("compact")
    visual_system_candidates_compact.add_argument("--status", choices=["pending", "confirmed", "ignored"])
    visual_system_candidates_compact.add_argument("--batch-id")
    visual_system_candidates_compact.set_defaults(func=cmd_visual_system_candidates_compact)

    recipe = sub.add_parser("recipe", help="Manage reusable visual recipes that combine memories.")
    recipe_sub = recipe.add_subparsers(required=True)
    recipe_create = recipe_sub.add_parser("create")
    recipe_create.add_argument("--json", required=True)
    recipe_create.set_defaults(func=cmd_recipe_create)
    recipe_list = recipe_sub.add_parser("list")
    recipe_list.add_argument("--system-id")
    recipe_list.add_argument("--status")
    recipe_list.add_argument("--query")
    recipe_list.add_argument("--limit", type=int, default=50)
    recipe_list.add_argument("--summary", action="store_true")
    recipe_list.set_defaults(func=cmd_recipe_list)
    recipe_get = recipe_sub.add_parser("get")
    recipe_get.add_argument("recipe_id")
    recipe_get.set_defaults(func=cmd_recipe_get)
    recipe_add_asset = recipe_sub.add_parser("add-asset")
    recipe_add_asset.add_argument("recipe_id")
    recipe_add_asset.add_argument("asset_id")
    recipe_add_asset.add_argument("--role", choices=["core", "optional", "avoid", "reference_only"], default="optional")
    recipe_add_asset.add_argument("--weight", type=float, default=0.5)
    recipe_add_asset.add_argument("--reason")
    recipe_add_asset.set_defaults(func=cmd_recipe_add_asset)
    recipe_merge_preview = recipe_sub.add_parser("merge-preview")
    recipe_merge_preview.add_argument("source_recipe_id")
    recipe_merge_preview.add_argument("target_recipe_id")
    recipe_merge_preview.set_defaults(func=cmd_recipe_merge_preview)
    recipe_merge = recipe_sub.add_parser("merge")
    recipe_merge.add_argument("source_recipe_id")
    recipe_merge.add_argument("target_recipe_id")
    recipe_merge.set_defaults(func=cmd_recipe_merge)
    recipe_evidence = recipe_sub.add_parser("evidence")
    recipe_evidence.add_argument("recipe_id")
    recipe_evidence.add_argument("--type")
    recipe_evidence.add_argument("--limit", type=int, default=50)
    recipe_evidence.add_argument("--summary", action="store_true")
    recipe_evidence.set_defaults(func=cmd_recipe_evidence)
    recipe_revisions = recipe_sub.add_parser("revisions")
    recipe_revisions.add_argument("recipe_id")
    recipe_revisions.add_argument("--limit", type=int, default=50)
    recipe_revisions.add_argument("--summary", action="store_true")
    recipe_revisions.set_defaults(func=cmd_recipe_revisions)
    recipe_candidates = recipe_sub.add_parser("candidates")
    recipe_candidates_sub = recipe_candidates.add_subparsers(required=True)
    recipe_candidates_list = recipe_candidates_sub.add_parser("list")
    recipe_candidates_list.add_argument("--batch-id")
    recipe_candidates_list.add_argument("--status")
    recipe_candidates_list.add_argument("--limit", type=int, default=50)
    recipe_candidates_list.add_argument("--summary", action="store_true")
    recipe_candidates_list.set_defaults(func=cmd_recipe_candidates_list)
    recipe_candidate_get = recipe_candidates_sub.add_parser("get")
    recipe_candidate_get.add_argument("candidate_id")
    recipe_candidate_get.set_defaults(func=cmd_recipe_candidate_get)
    recipe_candidate_confirm = recipe_candidates_sub.add_parser("confirm")
    recipe_candidate_confirm.add_argument("candidate_id")
    recipe_candidate_confirm.add_argument("--system-id", action="append")
    recipe_candidate_confirm.add_argument("--target-recipe-id")
    recipe_candidate_confirm.add_argument("--variant-of")
    recipe_candidate_confirm.add_argument(
        "--action",
        choices=["attach_evidence", "create_new", "inherit_variant", "merge_existing"],
    )
    recipe_candidate_confirm.add_argument("--force-new", action="store_true")
    recipe_candidate_confirm.set_defaults(func=cmd_recipe_candidate_confirm)
    recipe_candidate_ignore = recipe_candidates_sub.add_parser("ignore")
    recipe_candidate_ignore.add_argument("candidate_id")
    recipe_candidate_ignore.add_argument("--cleanup", action="store_true")
    recipe_candidate_ignore.set_defaults(func=cmd_recipe_candidate_ignore)
    recipe_candidate_delete = recipe_candidates_sub.add_parser("delete")
    recipe_candidate_delete.add_argument("candidate_id")
    recipe_candidate_delete.set_defaults(func=cmd_recipe_candidate_delete)
    recipe_candidates_cleanup = recipe_candidates_sub.add_parser("cleanup")
    recipe_candidates_cleanup.add_argument("--status", choices=["ignored"], default="ignored")
    recipe_candidates_cleanup.add_argument("--batch-id")
    recipe_candidates_cleanup.set_defaults(func=cmd_recipe_candidates_cleanup)
    recipe_candidates_compact = recipe_candidates_sub.add_parser("compact")
    recipe_candidates_compact.add_argument("--status", choices=["pending", "confirmed", "ignored"])
    recipe_candidates_compact.add_argument("--batch-id")
    recipe_candidates_compact.set_defaults(func=cmd_recipe_candidates_compact)

    asset = sub.add_parser("asset", help="Inspect local reference and generated image files.")
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

    prompt = sub.add_parser("prompt", help="Compose or save generation-ready prompts.")
    prompt_sub = prompt.add_subparsers(required=True)
    prompt_save = prompt_sub.add_parser("save", help="Save a complete prompt record from JSON.")
    prompt_save.add_argument("--json", required=True, help="Prompt record JSON path, or '-' for stdin.")
    prompt_save.set_defaults(func=cmd_prompt_save)
    prompt_compose = prompt_sub.add_parser(
        "compose",
        help="Refine a source prompt with optional visual memory context.",
        description=(
            "Compose a generation-ready prompt. You can pass a natural source prompt and optionally guide "
            "recall with a query, saved visual memory, visual system, or recipe."
        ),
    )
    prompt_compose.add_argument("--source-prompt", required=True, help="The user's original image prompt.")
    prompt_compose.add_argument("--asset-id", action="append", help="Saved visual memory ID to apply. Repeatable.")
    prompt_compose.add_argument("--system-id", action="append", help="Visual system ID to apply. Repeatable.")
    prompt_compose.add_argument("--recipe-id", action="append", help="Recipe ID to apply. Repeatable.")
    prompt_compose.add_argument("--query", help="Keywords used to recall related visual memory.")
    prompt_compose.add_argument("--aspect-ratio", help="Preferred image aspect ratio, such as 1:1, 3:4, or 16:9.")
    prompt_compose.add_argument("--target-generation-skill", help="Generation skill name to target.")
    prompt_compose.add_argument("--save", action="store_true", help="Save the composed prompt record.")
    prompt_compose.add_argument("--debug-recall", action="store_true", help="Include uncollapsed raw recall candidates for debugging.")
    prompt_compose.set_defaults(func=cmd_prompt_compose)

    generation = sub.add_parser("generation", help="Record and inspect image-generation history.")
    generation_sub = generation.add_subparsers(required=True)
    generation_record = generation_sub.add_parser("record", help="Record a generation or edit result from JSON.")
    generation_record.add_argument("--json", required=True, help="Generation run JSON path, or '-' for stdin.")
    generation_record.set_defaults(func=cmd_generation_record)
    generation_list = generation_sub.add_parser(
        "list",
        help="List recent image-generation records.",
        description="Show recent generation/edit history with prompt previews, output paths, review status, and feedback.",
    )
    generation_list.add_argument("--asset-id", help="Filter to generations using a specific visual memory ID.")
    generation_list.add_argument("--status", help="Filter by generation status, such as generated, edited, or failed.")
    generation_list.add_argument("--review", help="Filter by visual review result, such as pass or major_deviation.")
    generation_list.add_argument("--limit", type=int, default=20, help="Maximum records to return.")
    generation_list.set_defaults(func=cmd_generation_list)
    generation_get = generation_sub.add_parser("get")
    generation_get.add_argument("run_id")
    generation_get.add_argument("--summary", action="store_true")
    generation_get.set_defaults(func=cmd_generation_get)
    generation_stats = generation_sub.add_parser("stats")
    generation_stats.add_argument("--asset-id")
    generation_stats.set_defaults(func=cmd_generation_stats)
    generation_suggest = generation_sub.add_parser("suggest")
    generation_suggest.add_argument("run_id")
    generation_suggest.add_argument("--kind", choices=["recipe", "visual-system"])
    generation_suggest.add_argument("--auto", action="store_true")
    generation_suggest.set_defaults(func=cmd_generation_suggest)
    generation_feedback = generation_sub.add_parser("feedback")
    generation_feedback.add_argument("run_id")
    generation_feedback.add_argument("--liked", choices=["true", "false"])
    generation_feedback.add_argument("--notes")
    generation_feedback.set_defaults(func=cmd_generation_feedback)

    panel = sub.add_parser(
        "panel",
        help="Launch the local read-only visual memory panel.",
        description=(
            "Start a local read-only web panel for browsing saved visual assets, recipes, visual systems, "
            "reference images, and generated images."
        ),
    )
    panel.add_argument("--host", help="Panel host. Defaults to backend.host in config.")
    panel.add_argument("--port", type=int, help="Panel port. Defaults to backend.port in config.")
    panel.add_argument("--open", action="store_true", help="Open the panel URL in the default browser.")
    panel.add_argument("--quiet", action="store_true", help="Suppress HTTP request logs.")
    panel.set_defaults(func=cmd_panel)

    serve = sub.add_parser("serve", help="Alias for panel.")
    serve.add_argument("--host", help="Panel host override.")
    serve.add_argument("--port", type=int, help="Panel port override.")
    serve.add_argument("--open", action="store_true", help="Open the panel URL in the default browser.")
    serve.add_argument("--quiet", action="store_true", help="Suppress HTTP request logs.")
    serve.set_defaults(func=cmd_serve)

    validate = sub.add_parser("validate")
    validate.add_argument(
        "kind",
        choices=["visual-asset", "visual-asset-candidate", "visual-system", "recipe", "prompt", "generation"],
    )
    validate.add_argument("--json", required=True)
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
