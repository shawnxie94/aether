#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.composer import compose_prompt  # noqa: E402
from aether_core.config import ensure_configured_dirs, load_config  # noqa: E402
from aether_core.generation_params import apply_prompt_generation_params  # noqa: E402
from aether_core.storage import AetherStore  # noqa: E402
from aether_core.validation import validate_prompt_record  # noqa: E402

from save_prompt_record import build_confirmation_message  # noqa: E402


def read_overlay(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge_prompt_record(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = {**base, **overlay}
    for key in ("constraints", "intent_analysis", "intent_sketch", "recall_candidates", "recall_strategy", "composition_plan", "generation_params"):
        if isinstance(base.get(key), dict) and isinstance(overlay.get(key), dict):
            merged[key] = {**base[key], **overlay[key]}
    for key in ("selected_assets", "variants", "assumptions", "conflicts"):
        if key in overlay:
            merged[key] = overlay[key]
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-prompt", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--asset-id", action="append", default=[])
    parser.add_argument("--system-id", action="append", default=[])
    parser.add_argument("--recipe-id", action="append", default=[])
    parser.add_argument("--aspect-ratio")
    parser.add_argument("--target-generation-skill")
    parser.add_argument("--overlay-json", help="Optional prompt-record JSON overrides, or '-' for stdin.")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--emit-confirmation", action="store_true")
    parser.add_argument("--debug-recall", action="store_true", help="Include raw uncollapsed recall candidates in the output.")
    args = parser.parse_args()

    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()
    target_generation_skill = args.target_generation_skill or config.data.get("generation", {}).get("defaultGenerationSkill")
    record = compose_prompt(
        store,
        args.source_prompt,
        explicit_asset_ids=args.asset_id,
        system_ids=args.system_id,
        recipe_ids=args.recipe_id,
        query=args.query,
        aspect_ratio=args.aspect_ratio,
        target_generation_skill=target_generation_skill,
        default_generation_params=config.data.get("generation", {}).get("defaultParams", {}),
        config=config.data,
        include_debug_recall=args.debug_recall,
    )
    record = merge_prompt_record(record, read_overlay(args.overlay_json))
    record = apply_prompt_generation_params(record, config)
    validate_prompt_record(record)
    if args.save:
        record = store.save_prompt_record(record)
    output = (
        {"record": record, "confirmation_message": build_confirmation_message(record)}
        if args.emit_confirmation
        else record
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
