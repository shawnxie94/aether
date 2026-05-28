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
from aether_core.validation import validate_visual_asset_candidate  # noqa: E402


def read_payload(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def asset_summary(candidate: dict) -> dict:
    payload = candidate.get("payload", {})
    suggestion = payload.get("evolution_suggestion", {})
    action = payload.get("evolution_action") or suggestion.get("action")
    target_id = suggestion.get("target_id")
    if not target_id and action in {"attach_evidence", "inherit_variant", "merge_existing"}:
        target_id = candidate.get("target_asset_id")
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "type": candidate["type"],
        "name": candidate["name"],
        "status": candidate["status"],
        "evolution_action": action,
        "target_id": target_id,
        "dedupe_score": candidate["reuse_score"],
        "similar_candidate_count": len(candidate.get("similar_candidates", [])),
    }


def payload_candidate_summary(candidate: dict) -> dict:
    payload = candidate.get("payload", {})
    metadata = payload.get("metadata", {})
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "name": payload.get("name"),
        "status": candidate["status"],
        "recommendation": metadata.get("recommendation"),
        "evolution_action": metadata.get("evolution_action"),
        "target_id": metadata.get("target_system_id") or metadata.get("target_recipe_id"),
        "dedupe_score": metadata.get("dedupe_score"),
        "updated_at": candidate["updated_at"],
    }


def next_commands(batch_id: str, assets: list[dict], recipes: list[dict], systems: list[dict]) -> list[str]:
    commands = [
        f"aether visual-asset candidates list --batch-id {batch_id} --summary",
        f"aether visual-asset candidates confirm-batch {batch_id}",
    ]
    commands.extend(f"aether visual-asset candidates get {candidate['id']}" for candidate in assets)
    commands.extend(f"aether recipe candidates get {candidate['id']}" for candidate in recipes)
    commands.extend(f"aether visual-system candidates get {candidate['id']}" for candidate in systems)
    return commands


def build_summary(saved: dict) -> dict:
    assets = [asset_summary(candidate) for candidate in saved.get("candidate_assets", [])]
    recipes = [payload_candidate_summary(candidate) for candidate in saved.get("recipe_candidates", [])]
    systems = [payload_candidate_summary(candidate) for candidate in saved.get("visual_system_candidates", [])]
    return {
        "batch_id": saved["batch_id"],
        "candidate_assets": assets,
        "recipe_candidates": recipes,
        "visual_system_candidates": systems,
        "next_commands": next_commands(saved["batch_id"], assets, recipes, systems),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Candidate batch JSON path, or '-' for stdin.")
    parser.add_argument("--summary-only", action="store_true", help="Emit only the compact saved batch summary.")
    args = parser.parse_args()

    config = load_config()
    ensure_configured_dirs(config)
    payload = read_payload(args.json)
    validate_visual_asset_candidate(payload)
    store = AetherStore(config.database_path)
    store.init()
    saved = store.create_visual_asset_candidate_batch(payload, config=config.data)
    summary = build_summary(saved)
    output = summary if args.summary_only else {"batch": saved, "summary": summary}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
