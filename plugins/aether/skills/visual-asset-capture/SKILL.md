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

5. When one source image yields multiple complementary candidate assets, also produce `recipe_candidates` as source-derived recommendation drafts. A recipe candidate should reference candidate asset ids, not final visual asset ids, until the user confirms those assets.

Use `recipe_assets` entries shaped like:

```json
{
  "candidate_asset_id": "<candidate-id>",
  "role": "core",
  "weight": 0.8,
  "reason": "same source image and complementary visual role"
}
```

Keep source-derived recipe confidence moderate, usually `0.6` to `0.7`. Same-source co-occurrence is useful evidence, but not proof that the combination is always best.

6. When the parsed candidate assets plus recalled existing assets suggest a durable worldview, genre, series, or art direction, produce `visual_system_candidates`. Do not create a visual system automatically for every image.

Use this only when at least one of these is true:

- candidate assets cover several reusable roles, such as scene + style + palette
- related active assets are recalled from the existing library
- the source image also produced one or more recipe candidates
- the user explicitly frames the image as a world, series, IP, art direction, or genre reference

Visual system candidates should include:

- `kind`: `worldview`, `genre`, `series`, or `art_direction`
- `name`
- `summary`
- `visual_rules`
- `avoid_rules`
- `candidate_asset_relations`
- `existing_asset_relations`
- `related_existing_assets`
- `metadata.recommendation`: `suggest_create`

7. Validate visual asset drafts:

```bash
aether validate visual-asset-candidate --json <candidate-batch.json>
```

8. Persist the candidate batch before asking the user to decide. The storage layer will attach similarity suggestions against active assets of the same type, store recipe candidates, and can auto-suggest visual system candidates when no explicit `visual_system_candidates` are provided:

```bash
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate-id>
aether recipe candidates list --batch-id <batch-id>
aether visual-system candidates list --batch-id <batch-id>
```

9. Compare candidates against existing active visual assets by listing or searching matching type/tag/query when more context is needed:

```bash
aether visual-asset list --type <type> --status active --summary
aether visual-asset list --query "<keyword>" --summary
```

10. For each pending candidate, ask the user to confirm one of:

- create new visual asset
- attach as variant of an existing visual asset
- merge into an existing visual asset
- ignore as one-off content

11. If the user confirms the whole candidate batch, use the batch confirmation command. It confirms asset candidates first, then visual system candidates, then recipe candidates, and attaches recipes to newly confirmed systems when the recipe candidate has no explicit parent system:

```bash
aether visual-asset candidates confirm-batch <batch-id>
```

12. Save individual confirmed decisions through the candidate queue when the user wants to handle assets one by one:

```bash
aether visual-asset candidates decide <candidate-id> new_asset
aether visual-asset candidates decide <candidate-id> asset_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> existing_asset --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
```

13. After all recipe assets have been confirmed or mapped to existing assets, confirm source-derived recipe candidates:

```bash
aether recipe candidates confirm <recipe-candidate-id>
aether recipe candidates confirm <recipe-candidate-id> --system-id <visual-system-id>
```

14. After all visual system candidate assets have been confirmed or mapped to existing assets, confirm visual system candidates only if the user wants to create that higher-level system:

```bash
aether visual-system candidates get <visual-system-candidate-id>
aether visual-system candidates confirm <visual-system-candidate-id>
```

15. If the user confirms a direct branch or merge outside the candidate queue, use the explicit state commands:

```bash
aether visual-asset branch <parent-asset-id> --json <visual-asset.json>
aether visual-asset merge <source-asset-id> <target-asset-id>
aether visual-asset activate <visual-asset-id>
```

16. If a semantic similarity judgment was made outside the automatic candidate suggestions, save it:

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
