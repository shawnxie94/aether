---
name: aether-orchestrator
description: Default entrypoint for Aether plugin requests. Use for any Aether workflow, especially when the user provides images, source image prompts, fuzzy prompts, asks to capture style, browse existing styles, refine prompts, generate images, or is ambiguous. Route to style-library, style-capture, prompt-refine, or image-generate according to the request; image plus source-prompt inputs default to style-capture unless the user explicitly asks to generate a new image.
---

# Aether Orchestrator

Use this skill as the routing layer for Aether workflows.

## Routing

Choose exactly one primary route unless the user explicitly asks for a multi-step workflow.

| User input | Route |
| --- | --- |
| "列出风格", "风格列表", "已有风格", "查看风格库", "show/list/browse styles" | `style-library` |
| Request for a style's parameters, concrete definition, prompt template, negative prompt, or reference images | `style-library` |
| Reference image(s), screenshot(s), image file(s), optionally with source prompt(s) | `style-capture` |
| "沉淀", "记住", "保存风格", "分析风格", "判断是否已有", "style card" | `style-capture` |
| Text-only fuzzy image prompt asking for better wording, expansion, or model-ready prompt | `prompt-refine` |
| Explicit request to create, generate, render, or output a new image | `image-generate` |
| Image plus prompt, but no explicit request to create a new image | `style-capture` |
| Ambiguous image plus prompt request | `style-capture`, then ask before generating |

## Execution Rules

1. If the user provides image(s) and prompt text, treat the prompt as source metadata for style capture by default.
2. Do not call `image-generate` unless the user explicitly asks to generate/create/render/output a new image.
3. If the user asks to "沉淀并生成" or similar, run style capture first, then ask before starting paid or external generation.
4. Preserve user intent, source prompts, image paths, and notes when passing work into `style-capture`.
5. For the selected route, follow that route's `SKILL.md` workflow and use its bundled scripts when saving records.
6. If the request is missing required information, ask one concise question instead of guessing.

## Route Handoff

- For style library browsing, read and follow `../style-library/SKILL.md`.
- For style capture, read and follow `../style-capture/SKILL.md`.
- For prompt refinement, read and follow `../prompt-refine/SKILL.md`.
- For image generation, read and follow `../image-generate/SKILL.md`.
