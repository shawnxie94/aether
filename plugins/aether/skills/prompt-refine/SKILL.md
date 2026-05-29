---
name: prompt-refine
description: Use when the user gives a text-only fuzzy image-generation prompt or multi-image prompt set and wants Aether to refine it into one or more generation-ready prompts with selected or recommended visual assets using Codex as the refinement engine. If the user also provides reference image(s), prefer visual-asset-capture unless they explicitly ask only for text prompt refinement.
---

# Aether Prompt Refine

Use this skill to turn fuzzy image prompts into visual-asset-aware generation prompts. For multi-image requests, produce one shared prompt record with multiple per-image `variants`.

Load `references/refinement-rules.md` when deciding how far to expand or reinterpret a prompt.
Use `references/prompt-record-template.json` as the output shape.

## Workflow

1. Resolve config and inspect available visual assets:

```bash
aether config show
aether visual-asset list --status active --summary
aether visual-system list --status active --summary
aether recipe list --status active --summary
```

2. If the user specifies a reusable module, visual system, or recipe, load it:

```bash
aether visual-asset get <visual_asset_id>
aether visual-system get <visual_system_id>
aether recipe get <recipe_id>
```

3. Recall visual assets by type/query when they could improve the prompt:

```bash
aether visual-asset list --summary --status active
aether visual-asset list --type lighting --query "<keyword>" --summary
aether visual-asset get <visual_asset_id>
```

Prefer assets explicitly requested by the user, then assets matching the subject, scene, mood, target visual style, and historical generation quality.

For the default deterministic recall and composition pass, prefer the bundled compose script. It wraps `aether prompt compose`, merges optional overrides, validates the record, and can save with the same confirmation message used by `save_prompt_record.py`:

```bash
python skills/prompt-refine/scripts/compose_prompt_record.py --source-prompt "<prompt>" --query "<keywords>"
python skills/prompt-refine/scripts/compose_prompt_record.py --source-prompt "<prompt>" --asset-id <visual_asset_id> --save --emit-confirmation
python skills/prompt-refine/scripts/compose_prompt_record.py --source-prompt "<prompt>" --system-id <visual_system_id>
python skills/prompt-refine/scripts/compose_prompt_record.py --source-prompt "<prompt>" --recipe-id <recipe_id>
```

Use direct CLI composition only for debugging:

```bash
aether prompt compose --source-prompt "<prompt>" --query "<keywords>"
aether prompt compose --source-prompt "<prompt>" --asset-id <visual_asset_id> --save
aether prompt compose --source-prompt "<prompt>" --system-id <visual_system_id>
aether prompt compose --source-prompt "<prompt>" --recipe-id <recipe_id>
```

The composed output now includes an `intent_sketch`, `recall_candidates`, and `recall_strategy`. Treat `intent_sketch` as the first-stage structured interpretation of the user's prompt, then use recalled visual systems, recipes, and folded visual assets as controlled context for the final wording. `recall_candidates.visual_assets` is the default family-deduped list; `recall_candidates.visual_assets_raw` keeps the uncollapsed debug list. Use the composed output as the first draft, then let Codex improve wording while preserving `intent_sketch`, `selected_assets`, `constraints.selected_systems`, `constraints.selected_recipes`, `composition_plan`, `generation_params`, and `conflicts`.

4. Use Codex current model to analyze the source prompt:

- subject
- scene
- action
- mood
- composition and likely output format
- requested image count or sequence structure
- constraints
- missing assumptions

5. Refine the prompt by combining the user intent with selected visual assets. Preserve the user's subject, scene, action, emotion, and explicit constraints.

For single-image requests, write the final prompt in top-level `refined_prompt`, with `variants: []` unless a useful alternate wording is explicitly requested.

For multi-image requests, such as "三张图", carousel posts, storyboards, character turnarounds, comparison sets, batches of angles, or multiple scenes, write:

- top-level `refined_prompt`: shared series brief and continuity constraints
- top-level `negative_prompt`: shared negative constraints
- `variants[]`: one object per requested image, each with `id`, `title`, `refined_prompt`, `negative_prompt`, `generation_params`, `composition_plan`, optional `selected_assets`, and `notes`

Each variant must be independently generation-ready. Keep shared identity/style constraints consistent, but vary the requested angle, scene, pose, framing, moment, or shot-specific detail. If the user asks for N images, produce N variants unless the request is ambiguous; then ask one concise question.

Also recommend image generation parameters in `generation_params`. Always include `aspectRatio`; use an explicit user-requested ratio when present, otherwise choose the most suitable ratio for the composition. Fall back to `generation.defaultParams.aspectRatio` from config when there is no strong composition signal. Put the reason for the ratio recommendation in `assumptions`, not inside `generation_params`.

When selecting visual assets, keep the composition controlled:

- 1 style asset
- 1 color palette
- 1 lighting asset
- 1 composition asset
- 1 camera asset
- 1-2 mood assets
- 0-1 scene asset
- 0-2 texture, prop, or symbol assets
- 1 negative rule set

Check conflicts before writing the final prompt. If two assets conflict, preserve the user's explicit request first, then the selected style asset's invariants, then drop optional enhancement assets.

6. Validate and save a manually revised prompt record. Prefer the bundled save script when you already have a complete prompt-record JSON:

```bash
python skills/prompt-refine/scripts/save_prompt_record.py --json <prompt-record.json> --emit-confirmation
```

The JSON should include:

- `source_prompt`
- `target_generation_skill`
- `intent_sketch`
- `recall_candidates`
- `recall_strategy`
- `selected_assets`
- `constraints`
- `intent_analysis`
- `composition_plan`
- selected visual assets in `constraints.selected_assets`
- selected visual systems in `constraints.selected_systems`
- selected recipes in `constraints.selected_recipes`
- `refined_prompt`
- `negative_prompt`
- `generation_params`, including `aspectRatio`
- `variants`; for multi-image requests, one generation-ready object per image
- `assumptions`
- `conflicts`

## Rules

- Codex is the refinement engine; do not call or configure a separate LLM.
- Enhance visual language without replacing the user's core idea.
- Include assumptions when adding details the user did not specify.
- If no visual asset is provided, recommend a small coherent set of active visual assets and ask before applying them when the choice is not obvious.
- Do not over-compose with too many visual assets; prefer a small coherent set over a long keyword stack.
- Do not use a visual asset if it conflicts with explicit user constraints.
- If the user explicitly asked to generate image(s), save the prompt record first, relay the script's complete `confirmation_message` in natural language, including every prompt variant, shared/full negative prompt, suggested image params, and assumptions, then ask the user to confirm or revise before handing off to `image-generate`.
- Do not show raw prompt-record JSON, selected asset IDs, `composition_plan`, `generation_params`, or `conflicts` objects to non-technical users unless they ask for low-level details.
- Skip the confirmation checkpoint only when the user explicitly says to auto-generate after refinement.
- Do not use this as the default for reference image plus source-prompt inputs; use `visual-asset-capture` for visual asset sedimentation.
