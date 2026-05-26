#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.config import ensure_configured_dirs, load_config
from aether_core.generation_params import apply_prompt_generation_params
from aether_core.storage import AetherStore
from aether_core.validation import validate_prompt_record


def format_list(values: list) -> str:
    if not values:
        return "(none)"
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def build_confirmation_message(record: dict) -> str:
    generation_params = json.dumps(record.get("generation_params", {}), ensure_ascii=False, indent=2)
    return "\n".join(
        [
            f"Prompt record saved: `{record['id']}`",
            "",
            "**Refined Prompt**",
            "```text",
            record.get("refined_prompt", ""),
            "```",
            "",
            "**Negative Prompt**",
            "```text",
            record.get("negative_prompt", ""),
            "```",
            "",
            "**Assumptions**",
            "```text",
            format_list(record.get("assumptions", [])),
            "```",
            "",
            "**Suggested Image Params**",
            "```json",
            generation_params,
            "```",
            "",
            "Ask the user to confirm or revise this complete prompt before calling image-generate.",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Prompt record JSON path, or '-' for stdin.")
    parser.add_argument(
        "--emit-confirmation",
        action="store_true",
        help="Return a JSON wrapper containing the saved record and a complete confirmation markdown message.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_configured_dirs(config)
    payload = json.load(sys.stdin) if args.json == "-" else json.loads(Path(args.json).read_text(encoding="utf-8"))
    payload = apply_prompt_generation_params(payload, config)
    validate_prompt_record(payload)
    store = AetherStore(config.database_path)
    store.init()
    record = store.save_prompt_record(payload)
    output = (
        {"record": record, "confirmation_message": build_confirmation_message(record)}
        if args.emit_confirmation
        else record
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
