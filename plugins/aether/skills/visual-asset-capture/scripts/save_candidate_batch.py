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
    target_name = None
    if target_id:
        target_name = next(
            (
                item.get("name")
                for item in candidate.get("similar_candidates", [])
                if item.get("asset_id") == target_id
            ),
            None,
        )
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "type": candidate["type"],
        "name": candidate["name"],
        "status": candidate["status"],
        "evolution_action": action,
        "target_id": target_id,
        "target_name": target_name,
        "dedupe_score": candidate["reuse_score"],
        "similar_candidate_count": len(candidate.get("similar_candidates", [])),
    }


def payload_candidate_summary(candidate: dict) -> dict:
    payload = candidate.get("payload", {})
    metadata = payload.get("metadata", {})
    target_id = metadata.get("target_system_id") or metadata.get("target_recipe_id")
    target_name = None
    for field, id_key in (
        ("related_existing_systems", "system_id"),
        ("related_existing_recipes", "recipe_id"),
    ):
        target_name = next(
            (
                item.get("name")
                for item in payload.get(field, [])
                if item.get(id_key) == target_id
            ),
            None,
        )
        if target_name:
            break
    return {
        "id": candidate["id"],
        "batch_id": candidate["batch_id"],
        "name": payload.get("name"),
        "status": candidate["status"],
        "recommendation": metadata.get("recommendation"),
        "evolution_action": metadata.get("evolution_action"),
        "target_id": target_id,
        "target_name": target_name,
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


def readable_action(action: str | None) -> str:
    return {
        "create_new": "保存为新的视觉记忆",
        "attach_evidence": "归入已有视觉记忆，作为补充参考",
        "inherit_variant": "保存为已有视觉记忆的变体",
        "merge_existing": "建议和已有视觉记忆合并，合并前需要再次确认",
        "ignore": "忽略为一次性内容",
    }.get(action or "", action or "待判断")


def format_candidate_table(title: str, rows: list[dict]) -> list[str]:
    if not rows:
        return []
    lines = [
        f"**{title}**",
        "",
        "| 候选名称 | 召回相关 | 处理建议 |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        action = row.get("evolution_action") or row.get("recommendation")
        target = row.get("target_name") or "无明确召回目标"
        score = row.get("dedupe_score")
        related = target if score is None else f"{target}，相似度 {score:.2f}"
        lines.append(f"| {row.get('name') or '未命名'} | {related} | {readable_action(action)} |")
    return lines + [""]


def build_user_message(summary: dict) -> str:
    parts = [
        "参考图分析已经保存为待确认建议。",
        "",
        "下面是建议的处理方式；普通用户只需要确认保存方式，不需要关心内部编号。",
        "",
    ]
    parts.extend(format_candidate_table("视觉记忆建议", summary["candidate_assets"]))
    parts.extend(format_candidate_table("组合方式建议", summary["recipe_candidates"]))
    parts.extend(format_candidate_table("整体风格方向建议", summary["visual_system_candidates"]))
    parts.extend(
        [
            "你可以直接回复：全部确认、只保存某几项、把某项归入已有记忆，或忽略某项。",
        ]
    )
    return "\n".join(parts)


def build_summary(saved: dict) -> dict:
    assets = [asset_summary(candidate) for candidate in saved.get("candidate_assets", [])]
    recipes = [payload_candidate_summary(candidate) for candidate in saved.get("recipe_candidates", [])]
    systems = [payload_candidate_summary(candidate) for candidate in saved.get("visual_system_candidates", [])]
    summary = {
        "batch_id": saved["batch_id"],
        "candidate_assets": assets,
        "recipe_candidates": recipes,
        "visual_system_candidates": systems,
        "next_commands": next_commands(saved["batch_id"], assets, recipes, systems),
    }
    summary["user_message"] = build_user_message(summary)
    return summary


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
