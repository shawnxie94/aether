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
