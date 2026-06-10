---
name: visual-asset-capture
description: Use when the user provides reference images, screenshots, image files, or image-plus-source-prompt inputs and wants Aether to analyze, deduplicate, or save reusable visual asset candidates for confirmation. This is the default Aether route for image plus prompt inputs unless the user explicitly asks to generate or edit an output image. When the user explicitly asks to validate or tune the just-sedimented memory, also runs the optional post-confirmation consistency verification loop (step 7.5) that calls prompt-refine + image-generate to measure recipe_fidelity and, if the new run drifts, applies append-only tuning to the recipe and its assets.
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

7.5. (Optional) Post-confirmation consistency verification & tuning.

This step is **not** part of the default sedimentation flow. Only run it when the user explicitly asks to validate or tune the just-sedimented memory, e.g. phrases like "沉淀一下并生成一张验证", "verify the recipe", "check the assets actually transfer", or "tune if it drifts". The default confirmation flow ends at step 7.

7.5.1. Scope and loop budget

- Target: the just-confirmed visual assets, recipe, and visual system from this run (the active ids, not the candidate ids).
- Loop budget: at most 3 verification rounds. If fidelity stays below `high` after 3 rounds, stop and ask the user how to proceed. Do not silently keep tuning.
- Purpose: catch the common case where the visual memory looks correct on paper but drifts in generation (palette anchor pulls too hard, brushwork softens, specks over-spread, signature motif disappears, etc.).

7.5.2. Verification round

Goal: produce one generation run that exercises the recipe on a **new subject** (not a re-render of the reference image), then read the run's `visual_review.recipe_fidelity` to score how well the memory carried over.

1. Pick a probe subject. The subject must be different from the reference image's main subject so the test actually exercises the recipe's transferability. Keep the scene, palette, mood, and composition signals identical to the recipe. Example: if the reference was a curly-haired young woman on a vintage car, the probe can be a young man with glasses on a different color vintage car in the same Mediterranean hill town.
2. Call `prompt-refine` with the just-confirmed recipe / system ids and the probe source prompt, then save the prompt record.
3. Hand the prompt record to `image-generate` (the underlying image skill, e.g. `rightcodes-imagegen` or `imagegen`). Record the run.
4. Visually inspect the output. Required review fields (see `image-generate` step 6 for the full schema):
   - `visual_review.reviewed`: `true`
   - `visual_review.style_consistency`: `high` / `moderate` / `low` / `major_deviation`
   - `visual_review.recipe_fidelity`: `high` / `moderate` / `low` / `major_deviation` / `not_reviewed`
   - `visual_review.recipe_fidelity_score`: optional 0-1 number
   - `visual_review.matched_signature_traits`: list of signature traits that survived
   - `visual_review.deviations`: list of drifted traits
   - `visual_review.localized_deviations`: small region defects that do not need a full re-tune
5. Classify the round:
   - `recipe_fidelity: high` and `style_consistency: high` -> **pass**, stop the loop.
   - `recipe_fidelity: moderate` with one or two localized deviations -> **minor drift**, go to step 7.5.3 with the targeted L1-L2 actions.
   - `recipe_fidelity: low` or `major_deviation`, or any signature trait listed in the recipe's `must_cover_ratios` failed -> **major drift**, go to step 7.5.3 with the structural L3-L6 actions.
   - `recipe_fidelity: not_reviewed` or generation failed -> **inconclusive**, do not tune; ask the user how to proceed.

7.5.3. Tuning actions (append-only by default)

Tune from the cheapest to the most structural. Always prefer actions that keep the original confirmed assets intact and create branched / appended successors. Never silently edit the v1 profile or rename a confirmed recipe.

| Level | Action | When to use it | Aether command |
| --- | --- | --- | --- |
| L0 | Re-run with a sharper source prompt or a different probe subject. | Drift is a one-off sampling artefact, not a memory defect. | `prompt-refine` + `image-generate` again, no memory change. |
| L1 | Append a new composition rule to the recipe (`signature_self_check` or `must_cover_ratios`). | A specific signature trait disappeared or a number ratio failed. | `aether recipe update <recipe_id> --append-composition-rule '<json>'` |
| L2 | Add the missing v2 / branched asset to the recipe's `recipe_assets`. | A recallable visual asset already exists in storage but is not linked to the recipe. | `aether recipe add-asset <recipe_id> <visual_asset_id> --role core\|optional --weight <w> --reason "<why>"` |
| L3 | Branch a v2 of one specific visual asset that drifted. | A single asset's profile or prompt fragments do not describe the signature precisely enough. | `aether visual-asset branch <parent_asset_id> --json <v2.json>` then `aether visual-asset activate <v2_id>` |
| L4 | Branch v2 for the whole recipe or visual system. | Multiple L3 fixes are needed at once, or a whole-direction re-statement is required. | Use `visual-asset branch` per asset, then `aether visual-system create` a v2 system pointing at the v2 assets, then `aether visual-system merge <v1_id> <v2_id>` to retire v1, then archive v1 with the Aether storage helper. |
| L5 | Archive a superseded v1 / v2 so the active set collapses to one canonical row. | Only after a v2 / v3 exists and the user has confirmed the new canonical record is the one to keep. | `aether visual-asset archive <id>` for visual assets; for visual systems use the Aether storage helper `AetherStore.update_visual_system_status(<id>, "archived")`. The CLI does not expose system archive or activate; use the storage helper from a one-line Python script. |
| L6 | Rebuild the canonical record. | When the v1 / v2 lineage is too tangled to follow. Create a fresh v3 system with a clean name, link v2 assets to it, then archive v1 + v2 in one pass. | `aether visual-system create --json <v3.json>` + storage helper to set `active` + archive the older rows. |

Rules for tuning:

- Do not delete v1 / v2 visual assets; archive them. Archiving is reversible, deletion is not (no CLI command for visual asset delete exists; the only available exit is `archive`).
- Do not edit a confirmed visual asset's profile in place. Branch a v2 instead, so the v1 evidence is preserved for traceability.
- For recipes, always use `update --append-composition-rule`; never replace a v1 rule. v1 rules are part of the recipe's history.
- Every tuning round that mutates memory must be followed by another verification round (step 7.5.2). Do not declare success without re-running.
- Always record the verification run with `record_generation.py` and an honest `visual_review`. Mark the run as `liked: true` only when the user has approved the output, not because the run is a verification probe.

7.5.4. Termination

Stop the loop when one of the following is true:

- `recipe_fidelity: high` and the user accepts the output.
- Three rounds completed without reaching `high`. Stop, present the drift summary, and ask the user to pick the next action (manual prompt edit, more aggressive L4-L6 restructuring, or accept the current fidelity and move on).
- The user interrupts with "stop tuning" or similar.

When stopping on a pass, summarize for the user: which round passed, the final `recipe_fidelity_score`, the v2 / v3 record ids that were created, and which v1 / v2 ids were archived. Hide internal ids by default; show the localized readable names.

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
- Post-confirmation tuning (step 7.5) must be append-only: branch a v2 visual asset or v2 visual system, append a composition rule, or archive the older row. Never edit a confirmed visual asset's profile in place, never overwrite a confirmed recipe's composition rules, and never delete a confirmed record. Archiving is the only available soft-delete.

## When To Add Recipe Signature Coverage Rules

Recipes that lean on a specific visual signature (color split, dominant motif, signature negative space, signature material contrast) should also carry two extra `composition_rules` keys so the model gets hard numbers and self-check anchors instead of word-frequency heuristics:

- `must_cover_ratios`: list of quantifiable visual signal budgets, e.g. `"powder-blue pencil shading covers at least 35 percent of the upper frame (hair fringe, eye shadow, collar, or cup)"`.
- `signature_self_check`: list of single visual claims the model can confirm before producing the final image, e.g. `"iris shows a clear coral-red plus deep-blue split, not just 'highlights' or a single-hue eye"`.

The composer reads these two keys from the selected recipe, renders them into a dedicated "Recipe signature coverage:" paragraph, and appends the paragraph near the end of `refined_prompt` so the numbers survive prompt dilution. Future revisions of the recipe automatically pick up the same rules.

Use these keys when:

- The reference images share a single visible trait that is the recipe's main identity signal (e.g. red-blue iris split on a portrait recipe).
- Generation runs keep producing outputs that "look fine" but lost the signature trait.
- A consumer of the recipe needs a concrete checklist for `recipe_fidelity` review.

Do not add them when the recipe is meant to be style-agnostic (a composition-only recipe that should not lock in a palette).

A worked example lives at `plugins/aether/examples/recipe-with-signature-coverage.json`. To extend an existing recipe without rewriting it, use `aether recipe update <recipe_id> --append-composition-rule '<json>'` once per rule.
