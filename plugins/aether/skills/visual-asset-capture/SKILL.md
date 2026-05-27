---
name: visual-asset-capture
description: Use when the user sends one or more reference images, screenshots, or image files, optionally with the prompts that generated them, and wants Aether to analyze, deduplicate, or persist reusable visual assets. This is the default Aether skill for image plus prompt inputs unless the user explicitly asks to generate a new image.
---

# Aether Visual Asset Capture

Use this skill for Aether visual asset sedimentation.

Default to this skill when the user provides reference image(s) plus prompt text and does not explicitly ask to create a new output image.

Load `references/style-taxonomy.md` when deciding whether an observed trait is reusable visual language or one-off content.

## Workflow

1. Resolve the project config from the current workspace:

```bash
aether config show
```

2. Resolve and ingest reference images.

When local image paths are available, ingest them directly:

```bash
aether asset ingest --path <image-path> --kind reference
```

When the user provides a Codex chat attachment and no normal local image path is exposed, inspect the current Codex session JSONL for the corresponding user message. Chat attachments can appear as message content items shaped like:

```json
{"type": "input_image", "image_url": "data:image/png;base64,..."}
```

For these attachments:

- Prefer the bundled extraction script:

```bash
python skills/visual-asset-capture/scripts/extract_chat_attachment.py --reference-name <stable-reference-name>
```

- Use `--session <rollout-jsonl>` when the current session is not the newest file under `$CODEX_HOME/sessions`.
- The script extracts the `data:image/*;base64,...` payload, decodes it into `cacheDir/chat-attachments/<stable-reference-name>.<ext>`, ingests it as a `reference` asset, and emits a `source_reference` JSON object.
- Store the canonical ingested asset path from that output in `source_references[].image_path`.
- Preserve the original chat reference in `source_references[].original_image_path`, such as `chat_attachment:<stable-reference-name>`.
- Store `asset_id`, `sha256`, `mime_type`, and `size_bytes` on the source reference when available.
- Do not store the full base64 data URL in the visual asset source reference.
- Do not mark a chat attachment as "no local file path available" until this session-data extraction path has been checked.

3. Analyze all provided reference images with Codex vision. If the user also provides source prompts per image, treat them as clues, not ground truth.

4. Produce `candidate_assets` as the primary output. Classify each reusable visual module into one of:

- `style`
- `color_palette`
- `lighting`
- `composition`
- `camera`
- `mood`
- `scene`
- `texture`
- `character`
- `prop_symbol`
- `shape_line`
- `negative_rule`

Do not force all 12 types. Extract only reusable modules that would be useful for future prompt composition.

Each candidate asset should include:

- `type`
- `name`
- `summary`
- `tags`
- `profile`
- `source_references`
- `prompt_fragments`
- `negative_fragments`
- `compatible_with`
- `avoid_with`
- `recommended_aspect_ratios`
- `status`: `draft`

5. Validate visual asset drafts:

```bash
aether validate visual-asset-candidate --json <candidate-batch.json>
```

6. Persist the candidate batch before asking the user to decide. The storage layer will attach similarity suggestions against active assets of the same type:

```bash
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate-id>
```

7. Compare candidates against existing active visual assets by listing or searching matching type/tag/query when more context is needed:

```bash
aether visual-asset list --type <type> --status active --summary
aether visual-asset list --query "<keyword>" --summary
```

8. For each pending candidate, ask the user to confirm one of:

- create new visual asset
- attach as variant of an existing visual asset
- merge into an existing visual asset
- ignore as one-off content

9. Save confirmed decisions through the candidate queue:

```bash
aether visual-asset candidates decide <candidate-id> new_asset
aether visual-asset candidates decide <candidate-id> asset_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> existing_asset --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
```

10. If the user confirms a direct branch or merge outside the candidate queue, use the explicit state commands:

```bash
aether visual-asset branch <parent-asset-id> --json <visual-asset.json>
aether visual-asset merge <source-asset-id> <target-asset-id>
aether visual-asset activate <visual-asset-id>
```

11. If a semantic similarity judgment was made outside the automatic candidate suggestions, save it:

```bash
aether similarity save --json <similarity-result.json>
```

Use `source_asset_id` and `candidate_asset_id` in the similarity payload.

## Rules

- Do not treat one-off subject matter as style unless it recurs across references.
- For multiple references, separate common reusable visual traits from per-image differences.
- Do not perform irreversible merges without user confirmation.
- Preserve source prompts in `source_references` when provided.
- Preserve chat attachment images as ingested reference assets whenever the session exposes an `input_image` data URL.
- Do not persist candidate visual assets without user confirmation.
- Do not turn one-off subject matter into a long-term character, prop, or scene asset unless the user confirms it should recur.
- Do not call image-generation skills from this workflow unless the user asks to generate an image after visual asset capture is complete.
