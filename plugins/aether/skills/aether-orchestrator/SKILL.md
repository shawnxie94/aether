---
name: aether-orchestrator
description: Default entrypoint for Aether plugin requests. Use for any Aether workflow, especially when the user provides images, source image prompts, fuzzy prompts, asks to capture reusable visual assets, browse existing visual assets, refine prompts, generate images, or is ambiguous. Route to style-library, visual-asset-capture, prompt-refine, or image-generate according to the request; image plus source-prompt inputs default to visual-asset-capture unless the user explicitly asks to generate a new image.
---

# Aether Orchestrator

Use this skill as the routing layer for Aether workflows.

## Routing

Choose one primary route for single-stage tasks. Use a multi-step route when the user asks to generate from a raw or fuzzy text prompt, because generation must consume a refined prompt.

| User input | Route |
| --- | --- |
| "列出风格", "风格列表", "已有风格", "查看风格库", "show/list/browse styles", "素材列表", "素材库" | `style-library` |
| Request for a visual asset's parameters, concrete definition, prompt fragments, negative fragments, or reference images | `style-library` |
| Reference image(s), screenshot(s), image file(s), optionally with source prompt(s) | `visual-asset-capture` |
| "沉淀", "记住", "保存风格", "分析风格", "判断是否已有", "保存素材", "分析素材" | `visual-asset-capture` |
| Text-only fuzzy image prompt asking for better wording, expansion, or model-ready prompt | `prompt-refine` |
| Text-only raw/fuzzy image prompt plus explicit request to create, generate, render, or output a new image | `prompt-refine`, ask user to confirm the refined prompt, then `image-generate` |
| Request to generate from an already refined prompt, prompt record, or final model-ready prompt | `image-generate` |
| Request to use existing visual assets to generate a new subject from a short theme | `prompt-refine` with those assets, ask user to confirm the refined prompt, then `image-generate` |
| Image plus prompt, but no explicit request to create a new image | `visual-asset-capture` |
| Ambiguous image plus prompt request | `visual-asset-capture`, then ask before generating |

## Execution Rules

1. If the user provides image(s) and prompt text, treat the prompt as source metadata for visual asset capture by default.
2. Do not call `image-generate` unless the user explicitly asks to generate/create/render/output a new image.
3. Do not send a raw, fuzzy, or short subject prompt directly to `image-generate`; run `prompt-refine` first and save a prompt record.
4. When the user explicitly asks to generate and the input is a raw text prompt, save the prompt record, show the refined prompt, negative prompt, and assumptions, then ask the user to confirm or revise before calling `image-generate`.
5. Treat prompt refinement as a checkpoint before paid, external, or irreversible generation calls. Skip this confirmation only if the user explicitly says to auto-generate after refinement or asks to generate from an already confirmed prompt record.
6. If the user asks to "沉淀并生成" or similar, run `visual-asset-capture` first, then `prompt-refine` with the saved or selected visual assets, then ask before starting paid or external generation.
7. Preserve user intent, source prompts, image paths, and notes when passing work into `visual-asset-capture`.
8. For each selected route, follow that route's `SKILL.md` workflow and use its bundled scripts when saving records.
9. If the request is missing required information, ask one concise question instead of guessing.

## Route Handoff

- For style library browsing, read and follow `../style-library/SKILL.md`.
- For visual asset capture, read and follow `../visual-asset-capture/SKILL.md`.
- For prompt refinement, read and follow `../prompt-refine/SKILL.md`.
- For image generation, read and follow `../image-generate/SKILL.md`.
