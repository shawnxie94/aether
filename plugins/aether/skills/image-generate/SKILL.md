---
name: image-generate
description: Use only when the user explicitly asks Aether to create, generate, render, or output a new image from a refined prompt, then call the configured underlying Codex image skill and record the run. Do not use for uploaded/reference images, screenshots, style extraction, style sedimentation, or image plus source-prompt inputs; those should use style-capture.
---

# Aether Image Generate

Use this skill after a prompt has been refined and the user explicitly wants new image output recorded in Aether.

Load `references/generation-contract.md` if generation status or record fields are unclear.
Use `references/generation-run-template.json` as the output shape.

## Workflow

1. Resolve project config:

```bash
PYTHONPATH=src python -m aether_core.cli config show
```

2. Read `generation.defaultGenerationSkill` from `config.json`. This is the underlying Codex image skill to use, such as `imagegen` or `rightcodes-imagegen`.

3. Use the configured image skill to generate the image. If generation is unavailable or blocked, record a failed generation run with the error.

4. Validate and record the generation. Prefer the bundled script:

```bash
python skills/image-generate/scripts/record_generation.py --json <generation-run.json>
```

The JSON should include:

- `source_prompt`
- `refined_prompt`
- `negative_prompt`
- `style_id`
- `generation_skill`
- `skill_params`
- `skill_result_meta`
- `outputs`
- `status`: `generated` or `failed`
- `error` when failed

5. Ask the user for feedback. Save feedback when provided:

```bash
PYTHONPATH=src python -m aether_core.cli generation feedback <run_id> --liked true --notes "<notes>"
```

## Rules

- This skill is the Aether workflow skill. The actual image-generation capability is selected by `generation.defaultGenerationSkill`.
- If the user provided image(s) as references and did not explicitly ask for a new generated image, switch to `style-capture` instead.
- If the user only asks to analyze, remember, store, deduplicate, or extract style from image(s), switch to `style-capture` instead.
- Do not store provider secrets in Aether config.
- Always record success or failure so the generation history remains auditable.
