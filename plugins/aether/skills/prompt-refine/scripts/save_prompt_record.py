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
        return "无"
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def format_settings(settings: dict) -> str:
    if not settings:
        return "默认设置"
    readable = []
    labels = {
        "aspectRatio": "画面比例",
        "quality": "质量",
    }
    for key, value in settings.items():
        readable.append(f"{labels.get(key, key)}: {value}")
    return "，".join(readable)


def format_selected_assets(assets: list) -> str:
    if not assets:
        return "未指定长期视觉记忆。"
    lines = []
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            lines.append(f"{index}. {asset}")
            continue
        name = asset.get("name") or asset.get("summary") or asset.get("type") or "视觉记忆"
        kind = asset.get("type")
        label = f"{name}（{kind}）" if kind else name
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def compact_value(value) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        values = [compact_value(item) for item in value]
        return "；".join(item for item in values if item)
    if isinstance(value, dict):
        label = value.get("name") or value.get("summary") or value.get("kind") or value.get("type")
        if label:
            return str(label)
        return "；".join(
            f"{key}: {compact_value(item)}"
            for key, item in value.items()
            if key not in {"id", "asset_id", "system_id", "recipe_id"} and compact_value(item)
        )
    return str(value)


def format_named_items(items: list, fallback: str) -> str:
    if not items:
        return fallback
    lines = []
    for item in items:
        if not isinstance(item, dict):
            text = compact_value(item)
        else:
            name = item.get("name") or item.get("summary") or item.get("kind") or item.get("type") or fallback
            detail_parts = []
            if item.get("kind"):
                detail_parts.append(str(item["kind"]))
            if item.get("type"):
                detail_parts.append(str(item["type"]))
            if item.get("reason"):
                detail_parts.append(str(item["reason"]))
            text = str(name)
            if detail_parts:
                text += "（" + "，".join(detail_parts) + "）"
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else fallback


def format_memory_composition_preview(record: dict) -> str:
    plan = record.get("composition_plan", {})
    constraints = record.get("constraints", {})
    if not isinstance(plan, dict):
        plan = {}
    if not isinstance(constraints, dict):
        constraints = {}

    selected_assets = record.get("selected_assets", [])
    selected_systems = (
        plan.get("visual_systems")
        or constraints.get("selected_systems")
        or []
    )
    selected_recipes = (
        plan.get("recipes")
        or constraints.get("selected_recipes")
        or []
    )
    lines = [
        "这次生成会按下面的方式组合已选记忆，确认后再进入生图：",
        f"- 主体/场景: {compact_value(plan.get('subject')) or compact_value(plan.get('scene')) or '沿用原始需求'}",
        f"- 风格: {compact_value(plan.get('style')) or compact_value(plan.get('texture')) or compact_value(plan.get('shape_line')) or '未指定'}",
        f"- 色彩/光影: {compact_value([plan.get('color'), plan.get('lighting'), plan.get('palette_hints')]) or '未指定'}",
        f"- 构图/镜头: {compact_value([plan.get('composition'), plan.get('camera')]) or '未指定'}",
        f"- 情绪/角色/符号: {compact_value([plan.get('mood'), plan.get('character'), plan.get('symbols')]) or '未指定'}",
        f"- 负面规则: {compact_value(plan.get('negative_rules')) or compact_value(record.get('negative_prompt')) or '未指定'}",
        "- Recipe / Visual System:",
        format_named_items(selected_recipes, "  - 未使用 recipe"),
        format_named_items(selected_systems, "  - 未使用 visual system"),
        "- 参与组合的视觉资产:",
        format_named_items(selected_assets, "  - 未指定长期视觉记忆"),
    ]
    conflicts = record.get("conflicts") or constraints.get("conflicts") or []
    if conflicts:
        lines.extend(["- 需要确认的冲突:", format_list(conflicts)])
    return "\n".join(lines)


def format_variants(variants: list) -> str:
    if not variants:
        return "无"
    blocks = []
    for index, variant in enumerate(variants, start=1):
        if not isinstance(variant, dict):
            blocks.append(f"### Variant {index}\n\n```text\n{variant}\n```")
            continue
        label = variant.get("title") or variant.get("name") or variant.get("id") or f"Variant {index}"
        prompt = variant.get("refined_prompt") or variant.get("prompt") or ""
        negative_prompt = variant.get("negative_prompt", "")
        generation_params = format_settings(variant.get("generation_params", {}))
        composition_plan = variant.get("composition_plan", {})
        notes = format_list(variant.get("notes", []))
        composition_note = "；".join(f"{key}: {value}" for key, value in composition_plan.items()) or "无"
        blocks.append(
            "\n".join(
                [
                    f"### {index}. {label}",
                    "",
                    "**Prompt**",
                    "```text",
                    prompt,
                    "```",
                    "",
                    "**Negative Prompt**",
                    "```text",
                    negative_prompt,
                    "```",
                    "",
                    f"**建议设置**：{generation_params}",
                    "",
                    f"**构图要点**：{composition_note}",
                    "",
                    "**Notes**",
                    notes,
                ]
            )
        )
    return "\n\n".join(blocks)


def build_confirmation_message(record: dict) -> str:
    generation_params = format_settings(record.get("generation_params", {}))
    selected_assets = format_selected_assets(record.get("selected_assets", []))
    conflicts = format_list(record.get("conflicts", []))
    variants = record.get("variants", [])
    return "\n".join(
        [
            "提示词已经整理好。",
            "",
            "**使用的视觉记忆**",
            selected_assets,
            "",
            "**记忆组合预览**",
            format_memory_composition_preview(record),
            "",
            "**精修后的提示词**",
            "```text",
            record.get("refined_prompt", ""),
            "```",
            "",
            "**需要避免的内容**",
            "```text",
            record.get("negative_prompt", ""),
            "```",
            "",
            "**多图版本**",
            format_variants(variants),
            "",
            "**我做出的假设**",
            format_list(record.get("assumptions", [])),
            "",
            f"**建议图片设置**：{generation_params}",
            "",
            "**可能冲突或需要你确认的点**",
            conflicts,
            "",
            (
                "请用户确认这些版本是否可以开始生成，或指出要调整的地方。"
                if variants
                else "请用户确认这版提示词是否可以开始生成，或指出要调整的地方。"
            ),
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
