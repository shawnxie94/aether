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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pending", action="store_true", help="Include pending candidate queues.")
    parser.add_argument("--quality", action="store_true", help="Include visual asset quality summaries.")
    parser.add_argument("--recent-generations", type=int, default=0, help="Include the latest N generation runs.")
    parser.add_argument("--assets", action="store_true", help="Include active visual asset catalog.")
    parser.add_argument("--all", action="store_true", help="Include all report sections.")
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
        report["active_visual_assets"] = store.list_visual_assets(status="active", limit=None)
        report["visual_systems"] = store.list_visual_systems(status="active", limit=None)
        report["recipes"] = store.list_recipes(status="active", limit=None)
    if include_pending:
        report["pending"] = {
            "visual_asset_candidates": store.list_visual_asset_candidates(status="pending", limit=None),
            "visual_system_candidates": store.list_visual_system_candidates(status="pending", limit=None),
            "recipe_candidates": store.list_recipe_candidates(status="pending", limit=None),
        }
    if include_quality:
        report["quality"] = {
            asset["id"]: store.visual_asset_quality(asset["id"])
            for asset in store.list_visual_assets(limit=None)
        }
    if recent_generations:
        report["recent_generations"] = store.list_generation_runs(limit=recent_generations)
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
