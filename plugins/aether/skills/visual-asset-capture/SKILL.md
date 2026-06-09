---
name: visual-asset-capture
description: Use when the user provides reference images, screenshots, image files, or image-plus-source-prompt inputs and wants Aether to analyze, deduplicate, or save reusable visual asset candidates for confirmation. This is the default Aether route for image plus prompt inputs unless the user explicitly asks to generate or edit an output image.
---

# Aether Visual Asset Capture

Use this skill to turn reference images into reusable visual asset candidates, recipe candidates, and visual system candidates.

Default here when image input is paired with prompt text and the user did not explicitly ask for a new generated image.

Load:

- `references/style-taxonomy.md` when deciding whether an observed trait is reusable visual language or one-off content.
- `references/asset-schema-cheatsheet.md` when drafting candidate assets, recipe candidates, or visual system candidates.

Language policy:

- Reply to the user in the user's language.
- Save database-facing semantic fields in English, including candidate names, summaries, tags, profile values, prompt fragments, negative fragments, recipe/system rules, relation reasons, and metadata notes.
- Preserve source prompts, quoted text, proper nouns, file names, and source-reference user notes in their original language when they are evidence.
- In user-facing recommendation tables, hide persisted IDs by default and show localized readable object names. Database-facing names and IDs remain English/internal; only mention IDs when the user asks for low-level details or when a command needs an exact ID.

## Workflow

1. Resolve config:

```bash
aether config show
```

2. Resolve and ingest reference images.

For local paths:

```bash
aether asset ingest --path <image-path> --kind reference
```

For Codex chat attachments with no exposed local path, use the bundled extraction script before declaring that the image has no local file:

```bash
python skills/visual-asset-capture/scripts/extract_chat_attachment.py --reference-name <stable-reference-name>
```

Use `--session <rollout-jsonl>` when the current session is not the newest file under `$CODEX_HOME/sessions`. Store the emitted `source_reference` object in candidate payloads; never store the full base64 data URL.

3. Draft the candidate batch.

Use Codex vision to analyze the reference images. Treat source prompts as clues, not ground truth. First separate visible observations from reusable visual memory:

- `analysis_observations`: visible or explicitly inferred evidence for the reusable candidate. Include the trait, visible evidence, approximate image region, source reference id when available, `source`, `confidence`, and `reusable`.
- `excluded_observations`: visible one-off details that should not become reusable memory.
- `consensus`: for multiple references, record how many references support the trait, common traits, stable variants, and outliers.

Prefer `source: "visual_observation"` for traits directly seen in the image. Use `source: "source_prompt_hint"` only when a source prompt suggests a trait that is not visually certain, and lower the confidence. If a clean starting shape helps, generate a valid template:

```bash
python skills/visual-asset-capture/scripts/generate_candidate_template.py --asset-type <type> --name "<name>"
python skills/visual-asset-capture/scripts/generate_candidate_template.py --asset-type style --include-recipe --include-system
```

Candidate batch input should contain source-derived `candidate_assets`, and optionally `recipe_candidates` or `visual_system_candidates`. Do not prefill storage-owned recall or dedupe fields such as `related_existing_*`, `decision`, `reuse_score`, `target_asset_id`, `metadata.target_system_id`, or `metadata.target_recipe_id`.

4. Validate and persist the candidate batch before asking the user to decide.

Prefer the bundled save script because it validates, saves, and returns a compact decision summary plus next commands:

```bash
python skills/visual-asset-capture/scripts/save_candidate_batch.py --json <candidate-batch.json> --summary-only
```

The storage layer recomputes hybrid/embedding recall, writes `evolution_action`, stores recipe/system candidates, and can auto-suggest visual system candidates.
Relay the script's `user_message` to the user rather than dumping the raw JSON summary. Treat `batch_id`, candidate IDs, and `next_commands` as internal handoff details unless the user asks for technical details.

Use direct CLI commands only when debugging:

```bash
aether validate visual-asset-candidate --json <candidate-batch.json>
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --batch-id <batch-id> --summary
aether visual-asset candidates get <candidate-id>
aether recipe candidates list --batch-id <batch-id>
aether visual-system candidates list --batch-id <batch-id>
```

When presenting recommendations for the current sedimentation run, only use candidates from that run's `batch_id`. Do not use global `--status pending` candidate queues, because they can include older `generation_*` reuse suggestions or unrelated unfinished batches.

5. Inspect recall when a recommendation is unclear:

```bash
aether recall visual_asset --query "<candidate summary>"
aether recall visual_system --query "<candidate summary>"
aether recall recipe --query "<candidate summary>"
aether visual-asset list --type <type> --status active --summary
aether visual-asset list --query "<keyword>" --summary
```

> ⚠️ **HARD GATE — STOP HERE.** Do **not** run any of the following commands in this skill until the user has answered step 6:
>
> - `aether visual-asset candidates confirm-batch <batch-id>`
> - `aether visual-asset candidates decide <candidate-id> create_new`
> - `aether visual-asset candidates decide <candidate-id> inherit_variant --target-asset-id <parent-asset-id>`
> - `aether visual-asset candidates decide <candidate-id> attach_evidence --target-asset-id <existing-asset-id>`
> - `aether visual-asset candidates decide <candidate-id> merge_existing`
> - `aether recipe candidates confirm <recipe-candidate-id> [--force-new | --action ... | --variant-of ... | --target-recipe-id ...]`
> - `aether visual-system candidates confirm <visual-system-candidate-id> [--force-new | --action ...]`
> - `aether visual-asset merge <source> <target>`
> - `aether recipe merge <source> <target>`
> - `aether visual-system merge <source> <target>`
> - `aether visual-asset branch <parent-asset-id>`
>
> These commands write into long-term visual memory and are not trivially reversible. Persisting the candidate batch with `save_candidate_batch.py` is allowed before confirmation; confirming is not. When the storage layer suggests `inherit_variant` / `attach_evidence` / `merge_existing` but the user (or your own visual judgement) prefers a different action, present the option to the user — do not silently override the storage recommendation and confirm.

6. Ask the user to confirm one of these candidate actions:

- create new visual asset
- attach as evidence to an existing visual asset
- inherit as a variant of an existing visual asset
- merge existing visual assets after preview
- ignore as one-off content

When presenting sedimentation recommendations to the user, always use this fixed Markdown table format, grouped by candidate type. Omit an entire section only when there are no candidates of that type. Keep the surrounding explanation in the user's language and avoid exposing raw storage fields unless the user asks for them.

**Asset Candidates**

| 候选名称 | 召回相关 | 处理建议 |
| --- | --- | --- |
| `<localized_candidate_name>` | `<localized_target_name>`, action: `<evolution_action>`, score: `<dedupe_score>` | `<create_new / attach_evidence / inherit_variant / merge_existing / ignore>` plus a short reason |

**Recipe Candidates**

| 候选名称 | 召回相关 | 处理建议 |
| --- | --- | --- |
| `<localized_candidate_name>` | `<localized_target_recipe_name>`, action: `<evolution_action>`, score: `<dedupe_score>` | `<create_new / attach_evidence / inherit_variant / merge_existing / ignore>` plus a short reason |

**System Candidates**

| 候选名称 | 召回相关 | 处理建议 |
| --- | --- | --- |
| `<localized_candidate_name>` | `<localized_target_system_name>`, action: `<evolution_action>`, score: `<dedupe_score>` | `<create_new / attach_evidence / inherit_variant / merge_existing / ignore>` plus a short reason |

For every referenced existing asset, recipe, or system, show the localized readable name and hide the internal ID unless explicitly needed. If there is no recalled target, write `无明确召回目标`. Keep manual overrides visible when your recommendation differs from the storage layer's `evolution_action`.

For whole-batch confirmation:

```bash
aether visual-asset candidates confirm-batch <batch-id>
```

> **Idempotency warning:** `confirm-batch` persists asset candidates **and** the recipe / visual_system candidates in the same batch. After running it, every recipe candidate and visual_system candidate linked to `<batch-id>` will already be `confirmed` with a confirmed id. Do **not** run `aether recipe candidates confirm` or `aether visual-system candidates confirm` for those same candidate ids afterwards, or you will create duplicate recipes / systems (e.g. `recipe-name` and `recipe-name-2`). If a higher-level candidate was intentionally left out of the batch, or you need to re-decide one, run the per-id idempotency check in step 7 first.

For one-by-one decisions:

```bash
aether visual-asset candidates decide <candidate-id> create_new
aether visual-asset candidates decide <candidate-id> inherit_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> attach_evidence --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
aether visual-asset candidates decide <candidate-id> ignore --cleanup
aether visual-asset candidates cleanup --status ignored
```

7. Confirm higher-level recipe / visual_system candidates **only when** they were not already persisted by `confirm-batch`, or when the user explicitly wants a different decision (e.g. attach_evidence / inherit_variant / force_new). Before any separate confirm, run the idempotency check and skip the confirm if the candidate is already confirmed:

```bash
# Idempotency check — do this first for every recipe/system candidate id
aether recipe candidates get <recipe-candidate-id>
aether visual-system candidates get <visual-system-candidate-id>
```

If `status` is already `confirmed` and the linked `confirmed_recipe_id` / `confirmed_system_id` matches the desired target, do **not** call `confirm` again. The original target record (e.g. `recipe-quiet-sakura-youth-illustration-recipe`, not the `-2` copy) is the canonical survivor; a duplicate created by re-confirming can be cleaned up with `aether recipe merge <duplicate-id> <canonical-id>` / `aether visual-system merge <duplicate-id> <canonical-id>`.

```bash
aether recipe candidates confirm <recipe-candidate-id>
aether recipe candidates confirm <recipe-candidate-id> --system-id <visual-system-id>
aether recipe candidates confirm <recipe-candidate-id> --action attach_evidence --target-recipe-id <recipe-id>
aether recipe candidates confirm <recipe-candidate-id> --action inherit_variant --variant-of <recipe-id>
aether recipe candidates confirm <recipe-candidate-id> --force-new
aether recipe candidates ignore <recipe-candidate-id> --cleanup

aether visual-system candidates confirm <visual-system-candidate-id>
aether visual-system candidates confirm <visual-system-candidate-id> --action attach_evidence --target-system-id <visual-system-id>
aether visual-system candidates confirm <visual-system-candidate-id> --action inherit_variant --target-system-id <visual-system-id>
aether visual-system candidates confirm <visual-system-candidate-id> --force-new
aether visual-system candidates ignore <visual-system-candidate-id> --cleanup
```

8. Use explicit state commands for direct branch or merge work outside the candidate queue:

```bash
aether visual-asset branch <parent-asset-id> --json <visual-asset.json>
aether visual-asset merge-preview <source-asset-id> <target-asset-id>
aether visual-asset merge <source-asset-id> <target-asset-id>
aether recipe merge-preview <source-recipe-id> <target-recipe-id>
aether recipe merge <source-recipe-id> <target-recipe-id>
aether visual-system merge-preview <source-system-id> <target-system-id>
aether visual-system merge <source-system-id> <target-system-id>
aether visual-asset activate <visual-asset-id>
```

## Rules

- Do not treat one-off subject matter as a reusable asset unless the user confirms it should recur.
- For multiple references, separate common reusable visual traits from per-image differences.
- Persisting a candidate batch is allowed before user confirmation; confirming candidates into long-term assets, recipes, or systems requires user confirmation.
- Do not perform irreversible merges without user confirmation.
- Preserve source prompts in `source_references` when provided.
- Preserve chat attachment images as ingested reference assets whenever session data exposes an `input_image` data URL.
- Do not call image-generation skills from this workflow unless the user asks to generate an image after visual asset capture is complete.
