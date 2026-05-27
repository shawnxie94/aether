---
name: style-library
description: Use when the user asks to list, browse, search, inspect, or show existing Aether styles or generation history, including requests for a style's concrete parameter definition, prompt template, negative prompt, reference images, recent generations, visual review results, or generation stats.
---

# Aether Style Library

Use this skill to browse existing Aether style cards and generation history without creating, refining, or generating images.

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

## Generation History

When the user asks for recent generation history, use:

```bash
PYTHONPATH=src python -m aether_core.cli generation list
```

Useful filters:

```bash
PYTHONPATH=src python -m aether_core.cli generation list --style-id <style_id>
PYTHONPATH=src python -m aether_core.cli generation list --status generated
PYTHONPATH=src python -m aether_core.cli generation list --review major_deviation
PYTHONPATH=src python -m aether_core.cli generation list --limit 10
```

Present generation list rows with:

- `id`
- `style_id`
- `status`
- `prompt_preview`
- `aspect_ratio`
- `first_output`
- `style_consistency`
- `review_score`
- `recommendation`
- `liked`
- `updated_at`

When the user asks for a complete generation record, use:

```bash
PYTHONPATH=src python -m aether_core.cli generation get <generation_run_id>
```

When the user asks for generation quality or review trends, use:

```bash
PYTHONPATH=src python -m aether_core.cli generation stats
PYTHONPATH=src python -m aether_core.cli generation stats --style-id <style_id>
```

Summarize:

- total generation count
- status counts
- visual review counts
- liked/rejected/unrated counts
- per-style totals
- common deviations

## Rules

- Do not call `style-capture`, `prompt-refine`, or `image-generate` from this workflow unless the user asks for a follow-up action after browsing.
- Do not mutate style or generation records when the user only asks to list, inspect, or summarize.
- If the user names a style ambiguously, list matching candidates and ask one concise question.
- If there are no styles, say the style library is empty and suggest using `style-capture` only if the user wants to save a new style.
