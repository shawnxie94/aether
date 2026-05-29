---
name: visual-memory
description: Use when the user asks to browse, search, inspect, or summarize Aether's persisted visual memory, including visual assets, visual systems, recipes, candidates, generation history, evidence, quality stats, and local asset inventory.
---

# Aether Visual Memory Browser

Use this skill to browse Aether's persisted visual memory without creating, refining, mutating, or generating images.

## Language Policy

- Reply to the user in the user's language.
- Treat database-facing semantic fields as English by default. Existing records may contain legacy non-English names; display them as stored, but when proposing new or revised database records, write names, summaries, tags, prompt fragments, rules, relation reasons, and metadata notes in English.
- In user-facing summaries and recommendation tables, hide persisted IDs by default and show localized readable object names. Database-facing names and IDs remain English/internal; only mention IDs when the user asks for low-level details or when a command needs an exact ID.
- Preserve user-provided source text and proper nouns in their original language when they are evidence.

## Workflow

1. Resolve the project config:

```bash
aether config show
```

2. When the user asks for the available visual assets, style-like visual assets, asset list, memory list, or reusable modules, output visual assets as a compact catalog:

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

Present each asset with a human-readable name first and hide internal IDs by default. Only show an exact ID when the user asks for low-level details or when a follow-up command needs it.

Useful fields:

- `type`
- `name`
- `status`
- `summary`
- `tags`
- `prompt_fragment_count`
- `negative_fragment_count`
- `reference_count`
- `updated_at`

3. When the user asks for worlds, genres, series, art directions, or recommendation recipes, use:

```bash
aether visual-system list --summary
aether visual-system list --kind worldview --summary
aether recipe list --summary
aether recipe list --system-id <visual_system_id> --summary
```

Load details with:

```bash
aether visual-system get <visual_system_id>
aether recipe get <recipe_id>
```

Present visual systems and recipes with readable names first and hide exact IDs by default. Include the ID only when the user asks for low-level inspection or when a command needs it.

4. When the user asks for concrete definition, parameters, prompt recipe, negative prompt, or reference images, load the asset payload:

```bash
aether visual-asset get <visual_asset_id>
```

Present details in this order:

- name, id, type, status, summary, and tags
- structured `profile` as the concrete reusable parameter definition, using only keys allowed for the asset type
- `prompt_fragments`
- `negative_fragments`
- `compatible_with`
- `avoid_with`
- `recommended_aspect_ratios`
- reference images

5. For reference images, use `source_references[].image_path` or `source_references[].asset_path` when available. In Codex Desktop responses, show local reference images with Markdown image syntax:

```markdown
![<asset-name> reference <index>](/absolute/path/to/reference.png)
```

Also include source prompt, user note, role, or asset id when present.

## Candidate Queue And Quality

When the user asks for pending extracted modules or confirmation work:

```bash
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates list --batch-id <batch_id> --summary
aether visual-asset candidates get <candidate_id>
aether visual-asset candidates confirm-batch <batch_id>
aether visual-asset candidates decide <candidate_id> attach_evidence --target-asset-id <asset_id>
aether visual-asset candidates decide <candidate_id> inherit_variant --target-asset-id <asset_id>
aether visual-asset candidates decide <candidate_id> ignore --cleanup
aether visual-asset candidates cleanup --status ignored
aether recipe candidates list --status pending --summary
aether recipe candidates list --batch-id <batch_id> --summary
aether recipe candidates get <recipe_candidate_id>
aether recipe candidates confirm <recipe_candidate_id> --action attach_evidence --target-recipe-id <recipe_id>
aether recipe candidates confirm <recipe_candidate_id> --action inherit_variant --variant-of <recipe_id>
aether recipe candidates ignore <recipe_candidate_id>
aether recipe candidates ignore <recipe_candidate_id> --cleanup
aether recipe candidates cleanup --status ignored
aether visual-asset candidates compact --status confirmed
aether recipe candidates compact --status confirmed
aether visual-system candidates compact --status confirmed
aether visual-system candidates list --status pending --summary
aether visual-system candidates list --batch-id <batch_id> --summary
aether visual-system candidates get <visual_system_candidate_id>
aether visual-system candidates confirm <visual_system_candidate_id> --action attach_evidence --target-system-id <visual_system_id>
aether visual-system candidates confirm <visual_system_candidate_id> --action inherit_variant --target-system-id <visual_system_id>
aether visual-system candidates ignore <visual_system_candidate_id>
aether visual-system candidates ignore <visual_system_candidate_id> --cleanup
aether visual-system candidates cleanup --status ignored
```

If the user asks for recommendations for the current or just-finished sedimentation run, use the run's `batch_id` for all three candidate types. Do not mix in global pending queues or `generation_*` batches unless the user explicitly asks to review all pending work.

Present pending candidate recommendations in three separate Markdown tables: **Asset Candidates**, **Recipe Candidates**, and **System Candidates**. Each table must use exactly these columns: `候选名称`, `召回相关`, `处理建议`. Write every referenced item as its localized readable name and hide internal IDs unless explicitly needed; if there is no recalled target, write `无明确召回目标`. Keep `evolution_action`, `dedupe_score`, and any manual recommendation in the table cells so the user can compare candidates quickly.

When the user asks why an asset is being recommended or how it has performed:

```bash
aether visual-asset evidence <visual_asset_id>
aether visual-asset revisions <visual_asset_id>
aether recipe evidence <recipe_id>
aether recipe revisions <recipe_id>
aether visual-system evidence <visual_system_id>
aether visual-system revisions <visual_system_id>
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
python skills/visual-memory/scripts/memory_report.py --recent-generations 10
python skills/visual-memory/scripts/memory_report.py --pending --quality
python skills/visual-memory/scripts/memory_report.py --all
aether generation stats
aether generation stats --asset-id <visual_asset_id>
aether generation suggest <generation_run_id>
```

`memory_report.py` returns compact context-safe summaries by default. Use `--full` only for debugging or export work where full records are explicitly needed.

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
python skills/visual-memory/scripts/memory_report.py --all
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
- If there are no visual assets, say the visual memory is empty and suggest using `visual-asset-capture` only if the user wants to save new assets.
