---
name: prompt-refine
description: Use when the user gives a text-only fuzzy image-generation prompt and wants Aether to refine it with a selected or recommended style card using Codex as the refinement engine. If the user also provides reference image(s), prefer style-capture unless they explicitly ask only for text prompt refinement.
---

# Aether Prompt Refine

Use this skill to turn a fuzzy image prompt into a style-aware generation prompt.

Load `references/refinement-rules.md` when deciding how far to expand or reinterpret a prompt.
Use `references/prompt-record-template.json` as the output shape.

## Workflow

1. Resolve config and inspect available styles when needed:

```bash
PYTHONPATH=src python -m aether_core.cli config show
PYTHONPATH=src python -m aether_core.cli style list --status active
```

2. If the user specifies a style, load it:

```bash
PYTHONPATH=src python -m aether_core.cli style get <style_id>
```

3. Use Codex current model to analyze the source prompt:

- subject
- scene
- action
- mood
- composition and likely output format
- constraints
- missing assumptions

4. Refine the prompt by combining the user intent with the selected style card. Preserve the user's subject, scene, action, emotion, and explicit constraints.

Also recommend image generation parameters in `generation_params`. Always include `aspectRatio`; use an explicit user-requested ratio when present, otherwise choose the most suitable ratio for the composition. Fall back to `generation.defaultParams.aspectRatio` from config when there is no strong composition signal. Put the reason for the ratio recommendation in `assumptions`, not inside `generation_params`.

5. Optionally render from the stored style template before semantic refinement:

```bash
PYTHONPATH=src python -m aether_core.cli prompt render --style-id <style_id> --source-prompt "<prompt>"
```

6. Validate and save a prompt record. Prefer the bundled script:

```bash
python skills/prompt-refine/scripts/save_prompt_record.py --json <prompt-record.json> --emit-confirmation
```

The JSON should include:

- `source_prompt`
- `style_id`
- `target_generation_skill`
- `constraints`
- `intent_analysis`
- `refined_prompt`
- `negative_prompt`
- `generation_params`, including `aspectRatio`
- `variants`
- `assumptions`

## Rules

- Codex is the refinement engine; do not call or configure a separate LLM.
- Enhance visual language without replacing the user's core idea.
- Include assumptions when adding details the user did not specify.
- If no style is provided, recommend active styles and ask before applying one.
- If the user explicitly asked to generate an image, save the prompt record first, relay the script's complete `confirmation_message` including the full refined prompt, full negative prompt, suggested image params, and assumptions, then ask the user to confirm or revise before handing off to `image-generate`.
- Skip the confirmation checkpoint only when the user explicitly says to auto-generate after refinement.
- Do not use this as the default for reference image plus source-prompt inputs; use `style-capture` for style sedimentation.
