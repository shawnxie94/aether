#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.assets import ingest_asset
from aether_core.config import ensure_configured_dirs, load_config
from aether_core.similarity import compare_profiles, decision_for_score
from aether_core.storage import AetherStore
from aether_core.validation import validate_style


def read_json(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ingest_references(config, store: AetherStore, payload: dict) -> dict:
    references = []
    for reference in payload.get("source_references", []):
        image_path = reference.get("image_path") if isinstance(reference, dict) else None
        if not image_path or not Path(image_path).expanduser().exists():
            references.append(reference)
            continue
        asset_payload = ingest_asset(config, image_path, "reference")
        asset = store.create_asset(asset_payload)
        references.append(
            {
                **reference,
                "original_image_path": image_path,
                "image_path": asset["asset_path"],
                "asset_id": asset["id"],
                "sha256": asset["sha256"],
            }
        )
    payload["source_references"] = references
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Style card JSON path, or '-' for stdin.")
    parser.add_argument("--ingest-assets", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()
    payload = read_json(args.json)
    validate_style(payload)

    comparisons = []
    if args.compare:
        style_config = config.data.get("style", {})
        weights = style_config.get("similarityWeights", {})
        thresholds = style_config.get("similarityThresholds", {})
        for candidate in store.list_styles(status="active"):
            comparison = compare_profiles(payload.get("style_profile", {}), candidate["style_profile"], weights)
            comparisons.append(
                {
                    "candidate_style_id": candidate["id"],
                    "candidate_style_name": candidate["name"],
                    "similarity_score": comparison["similarity_score"],
                    "decision": decision_for_score(comparison["similarity_score"], thresholds),
                    "matched_dimensions": comparison["matched_dimensions"],
                    "different_dimensions": comparison["different_dimensions"],
                }
            )
        comparisons.sort(key=lambda item: item["similarity_score"], reverse=True)
        comparisons = comparisons[: args.limit]

    if args.ingest_assets:
        payload = ingest_references(config, store, payload)
    style = store.create_style(payload)
    if args.activate:
        style = store.update_style_status(style["id"], "active")

    json.dump({"style": style, "comparisons": comparisons}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

