---
name: style-library
description: Use when the user asks to list, browse, search, inspect, or show existing Aether styles, including requests for a style's concrete parameter definition, prompt template, negative prompt, or reference images.
---

# Aether Style Library

Use this skill to browse existing Aether style cards without creating, refining, or generating images.

## Workflow

1. Resolve the project config:

```bash
PYTHONPATH=src python -m aether_core.cli config show
```

2. When the user asks for the available style list, output all styles as a compact catalog:

```bash
PYTHONPATH=src python -m aether_core.cli style list --summary
```

Use `--status active` only when the user asks for active styles specifically.

3. Present each style with:

- `id`
- `name`
- `status`
- `summary`
- `tags`
- `reference_count`
- `updated_at`

4. When the user asks for a style's concrete definition, parameters, prompt recipe, negative prompt, or reference images, load the inspect payload:

```bash
PYTHONPATH=src python -m aether_core.cli style describe <style_id>
```

5. Present the details in this order:

- name, id, status, summary, and tags
- `style_profile` as the concrete reusable style parameter definition
- `prompt_template`
- `negative_prompt`
- reference images

6. For reference images, use `reference_images[].display_path` when available. In Codex Desktop responses, show local reference images with Markdown image syntax:

```markdown
![<style-name> reference <index>](/absolute/path/to/reference.png)
```

Also include source prompt, user note, role, or asset id when present.

## Rules

- Do not call `style-capture`, `prompt-refine`, or `image-generate` from this workflow unless the user asks for a follow-up action after browsing.
- Do not mutate style records when the user only asks to list or inspect styles.
- If the user names a style ambiguously, list matching candidates and ask one concise question.
- If there are no styles, say the style library is empty and suggest using `style-capture` only if the user wants to save a new style.
