#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.config import ensure_configured_dirs, load_config  # noqa: E402
from aether_core.storage import AetherStore  # noqa: E402


def text_preview(value: str, limit: int = 120) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def asset_summary(asset: dict) -> dict:
    return {
        "id": asset["id"],
        "type": asset["type"],
        "name": asset["name"],
        "summary": asset.get("summary", ""),
        "tags": asset.get("tags", []),
        "status": asset.get("status"),
        "prompt_fragment_count": len(asset.get("prompt_fragments", [])),
        "negative_fragment_count": len(asset.get("negative_fragments", [])),
    }


def system_summary(system: dict) -> dict:
    return {
        "id": system["id"],
        "kind": system["kind"],
        "name": system["name"],
        "summary": system.get("summary", ""),
        "status": system.get("status"),
        "asset_count": len(system.get("assets", [])),
        "visual_rule_count": len(system.get("visual_rules", [])),
        "avoid_rule_count": len(system.get("avoid_rules", [])),
    }


def recipe_summary(recipe: dict) -> dict:
    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "summary": recipe.get("summary", ""),
        "status": recipe.get("status"),
        "asset_count": len(recipe.get("assets", [])),
        "composition_rule_count": len(recipe.get("composition_rules", [])),
        "recommended_aspect_ratios": recipe.get("recommended_aspect_ratios", []),
    }


def candidate_summary(candidate: dict) -> dict:
    payload = candidate.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    suggestion = payload.get("evolution_suggestion", {}) if isinstance(payload, dict) else {}
    return {
        "id": candidate["id"],
        "batch_id": candidate.get("batch_id"),
        "name": candidate.get("name") or payload.get("name"),
        "type": candidate.get("type") or payload.get("type"),
        "status": candidate.get("status"),
        "evolution_action": payload.get("evolution_action") or metadata.get("evolution_action") or suggestion.get("action"),
        "target_id": suggestion.get("target_id") or metadata.get("target_system_id") or metadata.get("target_recipe_id"),
        "updated_at": candidate.get("updated_at"),
    }


def generation_summary(run: dict) -> dict:
    review = run.get("visual_review", {})
    outputs = run.get("outputs", [])
    first_output = ""
    if outputs:
        output = outputs[0]
        if isinstance(output, dict):
            first_output = output.get("image_path") or output.get("asset_path") or output.get("path") or output.get("url") or ""
        elif isinstance(output, str):
            first_output = output
    return {
        "id": run["id"],
        "mode": run.get("mode", "generate"),
        "status": run.get("status"),
        "selected_assets": run.get("selected_assets", []),
        "prompt_preview": text_preview(run.get("refined_prompt", "")),
        "output_count": len(outputs),
        "first_output": first_output,
        "style_consistency": review.get("style_consistency"),
        "review_score": review.get("score"),
        "recommendation": review.get("recommendation"),
        "liked": run.get("feedback", {}).get("liked"),
        "updated_at": run.get("updated_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pending", action="store_true", help="Include pending candidate queues.")
    parser.add_argument("--quality", action="store_true", help="Include visual asset quality summaries.")
    parser.add_argument("--recent-generations", type=int, default=0, help="Include the latest N generation runs.")
    parser.add_argument("--assets", action="store_true", help="Include active visual asset catalog.")
    parser.add_argument("--all", action="store_true", help="Include all report sections.")
    parser.add_argument("--full", action="store_true", help="Return full records instead of compact context-safe summaries.")
    args = parser.parse_args()

    include_assets = args.all or args.assets
    include_pending = args.all or args.pending
    include_quality = args.all or args.quality
    recent_generations = args.recent_generations if args.recent_generations else (10 if args.all else 0)

    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()

    report = {
        "config_path": str(config.path),
        "database_path": str(config.database_path),
    }
    if include_assets:
        assets = store.list_visual_assets(status="active", limit=None)
        systems = store.list_visual_systems(status="active", limit=None)
        recipes = store.list_recipes(status="active", limit=None)
        report["active_visual_assets"] = assets if args.full else [asset_summary(asset) for asset in assets]
        report["visual_systems"] = systems if args.full else [system_summary(system) for system in systems]
        report["recipes"] = recipes if args.full else [recipe_summary(recipe) for recipe in recipes]
    if include_pending:
        asset_candidates = store.list_visual_asset_candidates(status="pending", limit=None)
        system_candidates = store.list_visual_system_candidates(status="pending", limit=None)
        recipe_candidates = store.list_recipe_candidates(status="pending", limit=None)
        report["pending"] = {
            "visual_asset_candidates": asset_candidates if args.full else [candidate_summary(candidate) for candidate in asset_candidates],
            "visual_system_candidates": system_candidates if args.full else [candidate_summary(candidate) for candidate in system_candidates],
            "recipe_candidates": recipe_candidates if args.full else [candidate_summary(candidate) for candidate in recipe_candidates],
        }
    if include_quality:
        report["quality"] = {
            asset["id"]: store.visual_asset_quality(asset["id"])
            for asset in store.list_visual_assets(limit=None)
        }
    if recent_generations:
        generations = store.list_generation_runs(limit=recent_generations)
        report["recent_generations"] = generations if args.full else [generation_summary(run) for run in generations]
        report["generation_stats"] = store.generation_stats()
    if not any(key in report for key in ("active_visual_assets", "pending", "quality", "recent_generations")):
        report["summary"] = {
            "visual_asset_count": len(store.list_visual_assets(limit=None)),
            "visual_system_count": len(store.list_visual_systems(limit=None)),
            "recipe_count": len(store.list_recipes(limit=None)),
            "pending_visual_asset_candidate_count": len(store.list_visual_asset_candidates(status="pending", limit=None)),
        }

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
