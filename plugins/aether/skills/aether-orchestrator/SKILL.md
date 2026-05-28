---
name: aether-orchestrator
description: Default entrypoint for Aether plugin requests. Use for any Aether workflow, especially when the user provides images, source image prompts, fuzzy prompts, asks to capture reusable visual assets, browse persisted visual memory, refine prompts, generate images, edit generated images, or is ambiguous. Route to visual-memory, visual-asset-capture, prompt-refine, or image-generate according to the request; image plus source-prompt inputs default to visual-asset-capture unless the user explicitly asks to generate or edit an image.
---

# Aether Orchestrator

Use this skill as the routing layer for Aether workflows.

## Routing

Choose one primary route for single-stage tasks. Use a multi-step route when the user asks to generate from a raw or fuzzy text prompt, because generation must consume a refined prompt.

| User input | Route |
| --- | --- |
| "列出风格类视觉资产", "风格素材", "已有视觉资产", "查看素材库", "show/list/browse visual assets", "素材列表", "视觉记忆", "visual memory", "世界观", "流派", "系列", "推荐组合" | `visual-memory` |
| Request for a visual asset, visual system, recipe, candidate, generation history, evidence, quality stats, concrete definition, prompt fragments, negative fragments, or reference images | `visual-memory` |
| Reference image(s), screenshot(s), image file(s), optionally with source prompt(s) | `visual-asset-capture` |
| "沉淀", "记住", "保存风格类视觉资产", "分析可复用视觉特征", "判断是否已有", "保存素材", "分析素材" | `visual-asset-capture` |
| Text-only fuzzy image prompt asking for better wording, expansion, or model-ready prompt | `prompt-refine` |
| Text-only raw/fuzzy image prompt plus explicit request to create, generate, render, or output a new image | `prompt-refine`, ask user to confirm the refined prompt, then `image-generate` |
| Request to generate from an already refined prompt, prompt record, or final model-ready prompt | `image-generate` |
| Request to edit, fix, adjust, retouch, inpaint, or locally revise an existing generated image | `image-generate` with `mode: edit` |
| Visual review says the image is mostly usable but has local defects, broken details, or small region drift | recommend `image-generate` edit mode, then ask for confirmation |
| Request to use existing visual assets to generate a new subject from a short theme | `prompt-refine` with those assets, ask user to confirm the refined prompt, then `image-generate` |
| Image plus prompt, but no explicit request to create a new image | `visual-asset-capture` |
| Ambiguous image plus prompt request | `visual-asset-capture`, then ask before generating |

## Execution Rules

1. If the user provides image(s) and prompt text, treat the prompt as source metadata for visual asset capture by default.
2. Do not call `image-generate` unless the user explicitly asks to generate/create/render/output a new image.
3. Do not use `image-generate` edit mode unless the user asks to edit an existing image or confirms a targeted edit recommendation.
4. Do not send a raw, fuzzy, or short subject prompt directly to `image-generate`; run `prompt-refine` first and save a prompt record.
5. When the user explicitly asks to generate and the input is a raw text prompt, save the prompt record, show the refined prompt, negative prompt, and assumptions, then ask the user to confirm or revise before calling `image-generate`.
6. Treat prompt refinement as a checkpoint before paid, external, or irreversible generation calls. Skip this confirmation only if the user explicitly says to auto-generate after refinement or asks to generate from an already confirmed prompt record.
7. If the user asks to "沉淀并生成" or similar, run `visual-asset-capture` first, then `prompt-refine` with the saved or selected visual assets, then ask before starting paid or external generation.
8. Preserve user intent, source prompts, image paths, and notes when passing work into `visual-asset-capture`.
9. For each selected route, follow that route's `SKILL.md` workflow and use its bundled scripts when saving records.
10. If the request is missing required information, ask one concise question instead of guessing.

## Route Handoff

- For visual memory browsing, read and follow `../visual-memory/SKILL.md`.
- For visual asset capture, read and follow `../visual-asset-capture/SKILL.md`.
- For prompt refinement, read and follow `../prompt-refine/SKILL.md`.
- For image generation and generated-image editing, read and follow `../image-generate/SKILL.md`.
