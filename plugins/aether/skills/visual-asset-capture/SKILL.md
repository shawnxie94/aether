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

Use Codex vision to analyze the reference images. Treat source prompts as clues, not ground truth. If a clean starting shape helps, generate a valid template:

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

Use direct CLI commands only when debugging:

```bash
aether validate visual-asset-candidate --json <candidate-batch.json>
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate-id>
aether recipe candidates list --batch-id <batch-id>
aether visual-system candidates list --batch-id <batch-id>
```

5. Inspect recall when a recommendation is unclear:

```bash
aether recall visual_asset --query "<candidate summary>"
aether recall visual_system --query "<candidate summary>"
aether recall recipe --query "<candidate summary>"
aether visual-asset list --type <type> --status active --summary
aether visual-asset list --query "<keyword>" --summary
```

6. Ask the user to confirm one of these candidate actions:

- create new visual asset
- attach as evidence to an existing visual asset
- inherit as a variant of an existing visual asset
- merge existing visual assets after preview
- ignore as one-off content

For whole-batch confirmation:

```bash
aether visual-asset candidates confirm-batch <batch-id>
```

For one-by-one decisions:

```bash
aether visual-asset candidates decide <candidate-id> create_new
aether visual-asset candidates decide <candidate-id> inherit_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> attach_evidence --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
aether visual-asset candidates decide <candidate-id> ignore --cleanup
aether visual-asset candidates cleanup --status ignored
```

7. Confirm higher-level candidates only after their asset candidates have been confirmed or mapped:

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
