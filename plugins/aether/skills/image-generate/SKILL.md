---
name: image-generate
description: Use when the user explicitly asks Aether to create, generate, render, or output a new image from an already refined and user-confirmed prompt, or to edit/fix/adjust an existing generated image. Call the configured underlying Codex image skill and record the run. Do not use for raw/fuzzy text prompts before prompt-refine confirmation, and do not treat the original request to "generate" as confirmation. Do not use for uploaded/reference images, screenshots, visual asset extraction, visual asset sedimentation, or image plus source-prompt inputs unless the user explicitly asks to generate or edit an image; those should otherwise use visual-asset-capture.
---

# Aether Image Generate

Use this skill after a prompt has been refined and the user explicitly wants image output recorded in Aether.

## Required Preconditions

Before any provider call, confirm one of these is true:

- The user approved the refined prompt or prompt record in a later message.
- The user provided an already refined/final model-ready prompt and explicitly asked to generate from it.
- The user explicitly said to auto-generate after refinement.
- The request is an edit of an existing generated image and includes or implies a concrete edit instruction.

If the current turn just created a prompt record from a raw, fuzzy, short, or newly composed text prompt, do not generate yet. Return to `prompt-refine` confirmation instead. The user's original "generate/create/render" wording is not approval to skip this gate.

This skill supports two modes:

- `mode: generate`: first-pass text-to-image generation.
- `mode: edit`: targeted editing of an existing generated image while preserving accepted regions.

Load `references/generation-contract.md` if generation status or record fields are unclear.
Use `references/generation-run-template.json` as the output shape.

## Workflow

1. Resolve project config:

```bash
aether config show
```

2. Read `generation.defaultGenerationSkill` and `generation.defaultParams` from `config.json`. This is the underlying Codex image skill to use, such as `imagegen` or `rightcodes-imagegen`, plus default provider parameters such as `aspectRatio`.

3. Build the provider parameters before generation:

- Start with `generation.defaultParams`.
- If the request came from a prompt record, overlay `prompt_record.generation_params`.
- If generating from a prompt record variant, overlay `variant.generation_params` after prompt-level params.
- If the user explicitly overrides a parameter, overlay that last.
- Always carry the final `aspectRatio` into the underlying image-generation skill call when that skill supports an aspect ratio parameter.
- Store the same final parameter object in the generation run's `skill_params`.

4. Choose the operation mode.

Use `mode: generate` for new images.

When an approved prompt record contains `variants[]`, treat each variant as a separate generation run unless the user selects only specific variants. For each run, use the variant's `refined_prompt`, `negative_prompt`, `generation_params`, and `composition_plan`, falling back to the prompt record's top-level values for missing fields. Preserve lineage in `skill_result_meta` with `prompt_record_id`, `prompt_variant_id`, and `prompt_variant_title`.

Use `mode: edit` when the user asks to fix, retouch, adjust, inpaint, or locally revise an existing generated image. In edit mode:

- identify the source generation run or source image path
- preserve `source_generation_id` when available
- preserve `source_output_asset_id` when editing an archived generated asset
- write a concrete `edit_instruction`
- write `edit_regions` when the local defect or region is known
- preserve the source image's accepted subject, composition, style, lighting, palette, and aspect ratio unless the user explicitly asks to change them

Prefer edit mode when the overall image is acceptable and only local issues need correction. Prefer a new generate run when the subject, composition, camera angle, or global style is wrong.

5. Use the configured image skill to generate or edit the image. If generation/editing is unavailable or blocked, record a failed generation run with the error.

Generated image files must be archived into `generation.generatedImageDir` before the run is recorded. Pass local file paths, image URLs, data URLs, or output objects containing `asset_path`, `image_path`, `file_path`, `path`, or `url` in `outputs`; the recording script will copy/download/decode them into generated asset storage and replace `outputs` with archived asset metadata.

For transient provider failures, retry before giving up. Treat these as retryable unless the provider response clearly says the prompt is invalid or blocked:

- HTTP 408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524
- network timeouts
- connection resets
- empty provider responses

Default to `max_attempts = 3` with short backoff between attempts. Do not retry non-transient failures such as content policy blocks, authentication errors, quota exhaustion, invalid parameters, or user cancellation.

6. Run a visual style review before presenting the result as final.

If generation succeeded and selected visual assets are present, load each asset that has an `asset_id`:

```bash
aether visual-asset get <visual_asset_id>
```

Use Codex vision to inspect the generated output image(s) against the selected assets' `profile`, `prompt_fragments`, `negative_fragments`, and `source_references`. Compare reusable visual traits, not one-off subject content.

Write a `visual_review` object with:

- `reviewed`: `true`
- `style_consistency`: `pass`, `minor_deviation`, or `major_deviation`
- `score`: approximate 0-1 style consistency score
- `matched_traits`
- `deviations`
- `localized_deviations`: local defects that do not require replacing the whole image
- `recommendation`: `use`, `edit`, `revise_prompt`, or `regenerate`
- `suggested_revision`: prompt or parameter changes when needed
- `suggested_edit_instruction`: targeted edit instruction when local fixes are enough

If there is no output image, no selected visual assets, or the image cannot be inspected, set `reviewed: false`, `style_consistency: "not_reviewed"`, and explain why in `deviations`.

For local defects, do not recommend full regeneration by default. Use `recommendation: "edit"` when the overall image is usable but localized issues should be fixed through image editing, such as malformed hands, broken text, small object errors, localized style drift, face/detail repair, background cleanup, or a small composition adjustment. Include concrete `localized_deviations` and `suggested_edit_instruction`, then ask the user whether to run `image-generate` in edit mode.

For `major_deviation`, do not silently accept the image as style-consistent. Show the user the visual review, explain the drift, and recommend revising the prompt or regenerating.

7. Validate and record the generation/edit. Prefer the bundled script:

```bash
python skills/image-generate/scripts/record_generation.py --json <generation-run.json>
```

For a single retry attempt, record retry metadata:

```bash
python skills/image-generate/scripts/record_generation.py --json <generation-run.json> --attempt 1 --max-attempts 3 --retryable true
python skills/image-generate/scripts/record_generation.py --json <generation-run.json> --attempt 2 --max-attempts 3 --retry-of <previous-generation-run-id>
```

For multiple attempts already available as a manifest, prefer the bundled manifest script so retry lineage is chained automatically:

```bash
python skills/image-generate/scripts/record_generation_attempts.py --manifest <attempts-manifest.json>
```

Manifest shape:

```json
{
  "request_id": "logical_request_id",
  "max_attempts": 3,
  "attempts": [
    {"status": "failed", "retryable": true, "...": "..."},
    {"status": "generated", "retryable": false, "...": "..."}
  ]
}
```

The JSON should include:

- `source_prompt`
- `mode`: `generate` or `edit`
- `source_generation_id` for edits when available
- `source_output_asset_id` for edits when available
- `edit_instruction` for edits
- `edit_regions` for edits
- `refined_prompt`
- `negative_prompt`
- `selected_assets`
- `generation_skill`
- `skill_params`, including the final `aspectRatio`
- `skill_result_meta`
- `visual_review`
- `outputs`: archived generated asset metadata
- `status`: `generated`, `edited`, or `failed`
- `error` when failed

For variant-based generation, include `prompt_record` and put the variant lineage in `skill_result_meta`:

```json
{
  "prompt_record_id": "prompt_...",
  "prompt_variant_id": "variant_1",
  "prompt_variant_title": "Front View"
}
```

8. Ask the user for feedback. Save feedback when provided:

```bash
aether generation feedback <run_id> --liked true --notes "<notes>"
```

Generation recording automatically links generated outputs and visual review evidence back to each selected visual asset. Feedback recording adds user-feedback evidence. To inspect the resulting recommendation signal:

```bash
aether visual-asset evidence <visual_asset_id>
aether visual-asset quality <visual_asset_id>
aether generation suggest <run_id>
```

Successful reviewed generations can emit `reuse_suggestions` in the saved generation response. These suggestions are recipe or visual system candidates, not final long-term assets. Confirm them with the recipe or visual-system candidate commands when the user wants to preserve the generated combination.

When presenting results to the user, show the generated image, a short quality/style review, and a simple feedback question. Keep generation run IDs, archived asset metadata, retry fields, `skill_params`, and provider metadata internal unless the user asks for technical details.

## Rules

- This skill is the Aether workflow skill. The actual image-generation capability is selected by `generation.defaultGenerationSkill`.
- For edit mode, do not overwrite the source generated image. Always archive the edited output as a new generated asset.
- For edit mode, preserve source lineage with `source_generation_id` and `source_output_asset_id` whenever available.
- Do not drop `aspectRatio` between prompt refinement and generation. If a prompt record has `generation_params.aspectRatio`, use that over the config default.
- Always perform visual review for successful generations when an inspectable output image is available.
- Treat visual review as advisory. Do not automatically discard, overwrite, edit, or regenerate an image without user confirmation.
- Do not record successful generations with unarchived output images. Archive first, then save the generation run.
- Do not use this skill directly for a raw, fuzzy, or short text prompt; switch to `prompt-refine` first and come back with a refined prompt or saved prompt record.
- For a prompt record created in the same conversation turn, do not make a paid, external, provider-backed, or irreversible generation call unless the user explicitly opted into auto-generation after refinement before the record was created. Otherwise, stop and ask for confirmation.
- If the user provided image(s) as references and did not explicitly ask for a new generated image or an edit to an existing generated image, switch to `visual-asset-capture` instead.
- If the user only asks to analyze, remember, store, deduplicate, or extract reusable visual assets from image(s), switch to `visual-asset-capture` instead.
- Do not store provider secrets in Aether config.
- Always record success or failure so the generation history remains auditable.
- Retry transient generation failures up to the configured maximum and record each attempt, including the final success or final failure.
