#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.validation import (  # noqa: E402
    COMPOSITION_RULE_KEYS,
    VISUAL_ASSET_PROFILE_KEYS_BY_TYPE,
    VISUAL_ASSET_TYPES,
    VISUAL_RULE_KEYS_BY_KIND,
    validate_visual_asset_candidate,
)


def profile_template(asset_type: str) -> dict[str, str]:
    return {key: "" for key in sorted(VISUAL_ASSET_PROFILE_KEYS_BY_TYPE[asset_type])}


def candidate_asset_template(asset_type: str, name: str) -> dict:
    return {
        "id": f"asset_candidate_{asset_type}_example",
        "type": asset_type,
        "name": name,
        "summary": "",
        "tags": [],
        "profile": profile_template(asset_type),
        "source_references": [],
        "source_reference_ids": [],
        "prompt_fragments": [],
        "negative_fragments": [],
        "compatible_with": [],
        "avoid_with": [],
        "recommended_aspect_ratios": [],
        "status": "draft",
    }


def recipe_template(candidate_id: str) -> dict:
    return {
        "name": "Example Visual Recipe",
        "summary": "",
        "use_cases": [],
        "required_asset_types": [],
        "composition_rules": [
            {
                "key": sorted(COMPOSITION_RULE_KEYS)[0],
                "value": [],
                "reason": "",
            }
        ],
        "recommended_aspect_ratios": [],
        "source_reference_ids": [],
        "recipe_assets": [
            {
                "candidate_asset_id": candidate_id,
                "role": "core",
                "weight": 0.8,
                "reason": "",
            }
        ],
        "confidence": 0.65,
        "source": "same_reference_image",
        "reason": "",
        "status": "pending",
    }


def visual_system_template(candidate_id: str, kind: str) -> dict:
    return {
        "kind": kind,
        "name": "Example Visual System",
        "summary": "",
        "tags": [],
        "visual_rules": [
            {
                "key": sorted(VISUAL_RULE_KEYS_BY_KIND[kind])[0],
                "value": [],
                "reason": "",
            }
        ],
        "avoid_rules": [],
        "source_reference_ids": [],
        "candidate_asset_relations": [
            {
                "candidate_asset_id": candidate_id,
                "role": "core",
                "weight": 0.8,
                "reason": "",
            }
        ],
        "existing_asset_relations": [],
        "metadata": {
            "recommendation": "suggest_create",
            "reason": "",
        },
        "status": "pending",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-type", default="style", choices=sorted(VISUAL_ASSET_TYPES))
    parser.add_argument("--name", default="Example Visual Asset")
    parser.add_argument("--batch-id")
    parser.add_argument("--include-recipe", action="store_true")
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--system-kind", default="art_direction", choices=sorted(VISUAL_RULE_KEYS_BY_KIND))
    args = parser.parse_args()

    asset = candidate_asset_template(args.asset_type, args.name)
    payload = {
        "candidate_assets": [asset],
    }
    if args.batch_id:
        payload["batch_id"] = args.batch_id
    if args.include_recipe:
        payload["recipe_candidates"] = [recipe_template(asset["id"])]
    if args.include_system:
        payload["visual_system_candidates"] = [visual_system_template(asset["id"], args.system_kind)]

    validate_visual_asset_candidate(payload)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
