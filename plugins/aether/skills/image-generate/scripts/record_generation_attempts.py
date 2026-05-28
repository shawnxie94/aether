#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aether_core.config import ensure_configured_dirs, load_config  # noqa: E402
from aether_core.generation_params import apply_generation_skill_params  # noqa: E402
from aether_core.output_archiving import archive_generation_outputs  # noqa: E402
from aether_core.storage import AetherStore  # noqa: E402
from aether_core.validation import validate_generation_run  # noqa: E402

from record_generation import apply_visual_review_default  # noqa: E402


def read_manifest(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_attempt_metadata(
    payload: dict,
    attempt: int,
    max_attempts: int,
    retry_of: str | None,
    retryable: bool | None,
    request_id: str | None,
) -> dict:
    meta = payload.setdefault("skill_result_meta", {})
    retry = {
        "attempt": attempt,
        "max_attempts": max_attempts,
    }
    if request_id:
        retry["request_id"] = request_id
    if retry_of:
        retry["retry_of"] = retry_of
    if retryable is not None:
        retry["retryable"] = retryable
    meta["retry"] = {**meta.get("retry", {}), **retry}
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="Attempts manifest JSON path, or '-' for stdin.")
    args = parser.parse_args()

    manifest = read_manifest(args.manifest)
    attempts = manifest.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        raise SystemExit("Manifest must include a non-empty attempts array.")

    config = load_config()
    ensure_configured_dirs(config)
    store = AetherStore(config.database_path)
    store.init()

    max_attempts = int(manifest.get("max_attempts") or len(attempts))
    request_id = manifest.get("request_id")
    records = []
    previous_id = manifest.get("retry_of") or request_id
    for index, attempt_payload in enumerate(attempts, start=1):
        if not isinstance(attempt_payload, dict):
            raise SystemExit("Each attempt must be an object.")
        payload = dict(attempt_payload)
        retry_of = payload.pop("retry_of", previous_id if index > 1 else manifest.get("retry_of"))
        retryable = payload.pop("retryable", None)
        payload = apply_generation_skill_params(payload, config)
        payload = apply_attempt_metadata(payload, index, max_attempts, retry_of, retryable, request_id)
        payload = apply_visual_review_default(payload)
        validate_generation_run(payload)
        payload = archive_generation_outputs(config, store, payload)
        record = store.create_generation_run(payload)
        records.append(record)
        previous_id = record["id"]

    json.dump({"records": records, "final_record": records[-1]}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
