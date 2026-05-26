---
name: style-capture
description: Use when the user sends one or more reference images, optionally with source image-generation prompts, and wants Aether to analyze, deduplicate, and persist a reusable visual style card.
---

# Aether Style Capture

Use this skill for Aether style sedimentation.

Load `references/style-taxonomy.md` when deciding whether an observed trait is reusable style or one-off content.
Use `references/style-card-template.json` as the output shape.

## Workflow

1. Resolve the project config from the current workspace:

```bash
PYTHONPATH=src python -m aether_core.cli config show
```

2. Ingest provided image files when local paths are available:

```bash
PYTHONPATH=src python -m aether_core.cli asset ingest --path <image-path> --kind reference
```

3. Analyze all provided reference images with Codex vision. If the user also provides source prompts per image, treat them as clues, not ground truth.

4. Produce a style card draft with:

- `name`
- `summary`
- `tags`
- `source_references`: image path, optional source prompt, optional user note, role
- `style_profile`: art style, color palette, lighting, composition, mood, camera language, materials, era, line and shape, detail density, post processing, visual keywords, negative traits
- `prompt_template`
- `negative_prompt`
- `status`: `draft` unless the user explicitly confirms `active`

Use `references/style-card-template.json` as the output shape when needed.

5. Validate the style card draft:

```bash
PYTHONPATH=src python -m aether_core.cli validate style --json <style-card.json>
```

6. Compare the draft against existing active styles:

```bash
PYTHONPATH=src python -m aether_core.cli style compare --profile <draft-profile.json>
```

7. Explain the best matches and ask the user to confirm one of:

- merge into existing style
- create style branch
- create new style

8. Save the confirmed style card. Prefer the bundled script because it validates, optionally compares, ingests assets, and saves in one stable operation:

```bash
python skills/style-capture/scripts/save_style_card.py --json <style-card.json> --ingest-assets --compare
```

9. If the user confirms a branch or merge, use the explicit state commands:

```bash
PYTHONPATH=src python -m aether_core.cli style branch <parent-style-id> --json <style-card.json>
PYTHONPATH=src python -m aether_core.cli style merge <source-style-id> <target-style-id>
PYTHONPATH=src python -m aether_core.cli style activate <style-id>
```

10. If a semantic similarity judgment was made, save it:

```bash
PYTHONPATH=src python -m aether_core.cli similarity save --json <similarity-result.json>
```

## Rules

- Do not treat one-off subject matter as style unless it recurs across references.
- For multiple references, separate common style traits from per-image differences.
- Do not perform irreversible merges without user confirmation.
- Preserve source prompts in `source_references` when provided.
