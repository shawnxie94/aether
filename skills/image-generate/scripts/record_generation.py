#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.config import ensure_configured_dirs, load_config
from aether_core.storage import AetherStore
from aether_core.validation import validate_generation_run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Generation run JSON path, or '-' for stdin.")
    parser.add_argument("--liked", choices=["true", "false"])
    parser.add_argument("--notes")
    args = parser.parse_args()

    payload = json.load(sys.stdin) if args.json == "-" else json.loads(Path(args.json).read_text(encoding="utf-8"))
    validate_generation_run(payload)
    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()
    record = store.create_generation_run(payload)
    if args.liked is not None or args.notes:
        feedback = {}
        if args.liked is not None:
            feedback["liked"] = args.liked == "true"
        if args.notes:
            feedback["notes"] = args.notes
        status = "liked" if feedback.get("liked") is True else "rejected" if feedback.get("liked") is False else None
        record = store.update_generation_feedback(record["id"], feedback, status)
    json.dump(record, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

