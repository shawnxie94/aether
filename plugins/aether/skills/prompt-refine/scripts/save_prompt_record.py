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
from aether_core.validation import validate_prompt_record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Prompt record JSON path, or '-' for stdin.")
    args = parser.parse_args()

    payload = json.load(sys.stdin) if args.json == "-" else json.loads(Path(args.json).read_text(encoding="utf-8"))
    validate_prompt_record(payload)
    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()
    record = store.save_prompt_record(payload)
    json.dump(record, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

