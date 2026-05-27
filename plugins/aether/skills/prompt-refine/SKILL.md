---
name: prompt-refine
description: Use when the user gives a text-only fuzzy image-generation prompt and wants Aether to refine it with selected or recommended visual assets using Codex as the refinement engine. If the user also provides reference image(s), prefer visual-asset-capture unless they explicitly ask only for text prompt refinement.
---

# Aether Prompt Refine

Use this skill to turn a fuzzy image prompt into a visual-asset-aware generation prompt.

Load `references/refinement-rules.md` when deciding how far to expand or reinterpret a prompt.
Use `references/prompt-record-template.json` as the output shape.

## Workflow

1. Resolve config and inspect available visual assets:

```bash
aether config show
aether visual-asset list --status active --summary
```

2. If the user specifies a reusable module, load it:

```bash
aether visual-asset get <visual_asset_id>
```

3. Recall visual assets by type/query when they could improve the prompt:

```bash
aether visual-asset list --summary --status active
aether visual-asset list --type lighting --query "<keyword>" --summary
aether visual-asset get <visual_asset_id>
```

Prefer assets explicitly requested by the user, then assets matching the subject, scene, mood, target visual style, and historical generation quality.

For the default deterministic recall and composition pass, use:

```bash
aether prompt compose --source-prompt "<prompt>" --query "<keywords>"
aether prompt compose --source-prompt "<prompt>" --asset-id <visual_asset_id> --save
```

Use the composed output as the first draft, then let Codex improve wording while preserving `selected_assets`, `composition_plan`, `generation_params`, and `conflicts`.

4. Use Codex current model to analyze the source prompt:

- subject
- scene
- action
- mood
- composition and likely output format
- constraints
- missing assumptions

5. Refine the prompt by combining the user intent with selected visual assets. Preserve the user's subject, scene, action, emotion, and explicit constraints.

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

6. Validate and save a prompt record. Prefer the bundled script:

```bash
python skills/prompt-refine/scripts/save_prompt_record.py --json <prompt-record.json> --emit-confirmation
```

The JSON should include:

- `source_prompt`
- `target_generation_skill`
- `selected_assets`
- `constraints`
- `intent_analysis`
- `composition_plan`
- selected visual assets in `constraints.selected_assets`
- `refined_prompt`
- `negative_prompt`
- `generation_params`, including `aspectRatio`
- `variants`
- `assumptions`
- `conflicts`

## Rules

- Codex is the refinement engine; do not call or configure a separate LLM.
- Enhance visual language without replacing the user's core idea.
- Include assumptions when adding details the user did not specify.
- If no visual asset is provided, recommend a small coherent set of active visual assets and ask before applying them when the choice is not obvious.
- Do not over-compose with too many visual assets; prefer a small coherent set over a long keyword stack.
- Do not use a visual asset if it conflicts with explicit user constraints.
- If the user explicitly asked to generate an image, save the prompt record first, relay the script's complete `confirmation_message` including the full refined prompt, full negative prompt, suggested image params, and assumptions, then ask the user to confirm or revise before handing off to `image-generate`.
- Skip the confirmation checkpoint only when the user explicitly says to auto-generate after refinement.
- Do not use this as the default for reference image plus source-prompt inputs; use `visual-asset-capture` for visual asset sedimentation.
