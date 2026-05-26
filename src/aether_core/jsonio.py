from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def read_json_arg(value: str) -> Any:
    if value == "-":
        return json.load(sys.stdin)
    with Path(value).expanduser().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)

