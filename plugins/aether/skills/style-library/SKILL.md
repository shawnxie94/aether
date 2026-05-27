---
name: style-library
description: Use when the user asks to list, browse, search, inspect, or show existing Aether visual assets or generation history, including requests for a reusable asset's concrete parameter definition, prompt fragments, negative fragments, reference images, recent generations, visual review results, or generation stats.
---

# Aether Visual Asset Library

Use this skill to browse existing Aether visual assets and generation history without creating, refining, or generating images.

## Workflow

1. Resolve the project config:

```bash
aether config show
```

2. When the user asks for the available style list, asset list, or reusable modules, output visual assets as a compact catalog:

```bash
aether visual-asset list --summary
```

Useful filters:

```bash
aether visual-asset list --type style --summary
aether visual-asset list --type lighting --summary
aether visual-asset list --status active --summary
aether visual-asset list --query "<keyword>" --summary
aether visual-asset list --tag "<tag>" --summary
```

Present each asset with:

- `id`
- `type`
- `name`
- `status`
- `summary`
- `tags`
- `prompt_fragment_count`
- `negative_fragment_count`
- `reference_count`
- `updated_at`

3. When the user asks for concrete definition, parameters, prompt recipe, negative prompt, or reference images, load the asset payload:

```bash
aether visual-asset get <visual_asset_id>
```

Present details in this order:

- name, id, type, status, summary, and tags
- `profile` as the concrete reusable parameter definition
- `prompt_fragments`
- `negative_fragments`
- `compatible_with`
- `avoid_with`
- `recommended_aspect_ratios`
- reference images

4. For reference images, use `source_references[].image_path` or `source_references[].asset_path` when available. In Codex Desktop responses, show local reference images with Markdown image syntax:

```markdown
![<asset-name> reference <index>](/absolute/path/to/reference.png)
```

Also include source prompt, user note, role, or asset id when present.

## Candidate Queue And Quality

When the user asks for pending extracted modules or confirmation work:

```bash
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate_id>
```

When the user asks why an asset is being recommended or how it has performed:

```bash
aether visual-asset evidence <visual_asset_id>
aether visual-asset quality <visual_asset_id>
```

## Generation History

When the user asks for recent generation history, use:

```bash
aether generation list
```

Useful filters:

```bash
aether generation list --asset-id <visual_asset_id>
aether generation list --status generated
aether generation list --review major_deviation
aether generation list --limit 10
```

Present generation list rows with:

- `id`
- `mode`
- `source_generation_id`
- `source_output_asset_id`
- `selected_assets`
- `status`
- `prompt_preview`
- `edit_instruction_preview`
- `aspect_ratio`
- `first_output`
- `style_consistency`
- `review_score`
- `recommendation`
- `liked`
- `updated_at`

When the user asks for a complete generation record, use:

```bash
aether generation get <generation_run_id>
```

When the user asks for generation quality or review trends, use:

```bash
aether generation stats
aether generation stats --asset-id <visual_asset_id>
```

Summarize:

- total generation count
- status counts
- visual review counts
- liked/rejected/unrated counts
- per-asset totals
- common deviations

## Asset Governance

When the user asks about local asset size, duplicates, generated image inventory, or cleanup candidates, use the read-only asset commands:

```bash
aether asset list --kind generated
aether asset stats
aether asset duplicates --kind generated
aether asset unreferenced --kind generated
```

Report unreferenced assets as cleanup candidates only. Do not delete files or database rows unless the user explicitly asks for deletion.

## Rules

- Do not call `visual-asset-capture`, `prompt-refine`, or `image-generate` from this workflow unless the user asks for a follow-up action after browsing.
- Do not mutate visual assets or generation records when the user only asks to list, inspect, or summarize.
- If the user names an asset ambiguously, list matching candidates and ask one concise question.
- If there are no visual assets, say the visual asset library is empty and suggest using `visual-asset-capture` only if the user wants to save new assets.
