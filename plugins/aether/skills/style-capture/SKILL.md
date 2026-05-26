---
name: style-capture
description: Use when the user sends one or more reference images, screenshots, or image files, optionally with the prompts that generated them, and wants Aether to analyze, deduplicate, or persist reusable visual style. This is the default Aether skill for image plus prompt inputs unless the user explicitly asks to generate a new image.
---

# Aether Style Capture

Use this skill for Aether style sedimentation.

Default to this skill when the user provides reference image(s) plus prompt text and does not explicitly ask to create a new output image.

Load `references/style-taxonomy.md` when deciding whether an observed trait is reusable style or one-off content.
Use `references/style-card-template.json` as the output shape.

## Workflow

1. Resolve the project config from the current workspace:

```bash
PYTHONPATH=src python -m aether_core.cli config show
```

2. Resolve and ingest reference images.

When local image paths are available, ingest them directly:

```bash
PYTHONPATH=src python -m aether_core.cli asset ingest --path <image-path> --kind reference
```

When the user provides a Codex chat attachment and no normal local image path is exposed, inspect the current Codex session JSONL for the corresponding user message. Chat attachments can appear as message content items shaped like:

```json
{"type": "input_image", "image_url": "data:image/png;base64,..."}
```

For these attachments:

- Prefer the bundled extraction script:

```bash
python skills/style-capture/scripts/extract_chat_attachment.py --reference-name <stable-reference-name>
```

- Use `--session <rollout-jsonl>` when the current session is not the newest file under `$CODEX_HOME/sessions`.
- Use `--style-id <style-id>` after a style is saved when an existing style reference needs to be patched in place.
- The script extracts the `data:image/*;base64,...` payload, decodes it into `cacheDir/chat-attachments/<stable-reference-name>.<ext>`, ingests it as a `reference` asset, and emits a `source_reference` JSON object.
- Store the canonical ingested asset path from that output in `source_references[].image_path`.
- Preserve the original chat reference in `source_references[].original_image_path`, such as `chat_attachment:<stable-reference-name>`.
- Store `asset_id`, `sha256`, `mime_type`, and `size_bytes` on the source reference when available.
- Do not store the full base64 data URL in the style card.
- Do not mark a chat attachment as "no local file path available" until this session-data extraction path has been checked.

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
- Preserve chat attachment images as ingested reference assets whenever the session exposes an `input_image` data URL.
- Do not call image-generation skills from this workflow unless the user asks to generate an image after style capture is complete.
