---
name: image-generate
description: Use only when the user explicitly asks Aether to create, generate, render, or output a new image from a refined prompt, then call the configured underlying Codex image skill and record the run. Do not use for uploaded/reference images, screenshots, style extraction, style sedimentation, or image plus source-prompt inputs; those should use style-capture.
---

# Aether Image Generate

Use this skill after a prompt has been refined and the user explicitly wants new image output recorded in Aether.

Load `references/generation-contract.md` if generation status or record fields are unclear.
Use `references/generation-run-template.json` as the output shape.

## Workflow

1. Resolve project config:

```bash
PYTHONPATH=src python -m aether_core.cli config show
```

2. Read `generation.defaultGenerationSkill` and `generation.defaultParams` from `config.json`. This is the underlying Codex image skill to use, such as `imagegen` or `rightcodes-imagegen`, plus default provider parameters such as `aspectRatio`.

3. Build the provider parameters before generation:

- Start with `generation.defaultParams`.
- If the request came from a prompt record, overlay `prompt_record.generation_params`.
- If the user explicitly overrides a parameter, overlay that last.
- Always carry the final `aspectRatio` into the underlying image-generation skill call when that skill supports an aspect ratio parameter.
- Store the same final parameter object in the generation run's `skill_params`.

4. Use the configured image skill to generate the image. If generation is unavailable or blocked, record a failed generation run with the error.

Generated image files must be archived into `generation.generatedImageDir` before the run is recorded. Pass local file paths, image URLs, data URLs, or output objects containing `asset_path`, `image_path`, `file_path`, `path`, or `url` in `outputs`; the recording script will copy/download/decode them into generated asset storage and replace `outputs` with archived asset metadata.

For transient provider failures, retry before giving up. Treat these as retryable unless the provider response clearly says the prompt is invalid or blocked:

- HTTP 408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524
- network timeouts
- connection resets
- empty provider responses

Default to `max_attempts = 3` with short backoff between attempts. Do not retry non-transient failures such as content policy blocks, authentication errors, quota exhaustion, invalid parameters, or user cancellation.

5. Run a visual style review before presenting the result as final.

If generation succeeded and `style_id` is present, load the style card:

```bash
PYTHONPATH=src python -m aether_core.cli style get <style_id>
```

Use Codex vision to inspect the generated output image(s) against the style card's `style_profile`, `negative_prompt`, and `source_references`. Compare reusable visual style traits, not one-off subject content.

Write a `visual_review` object with:

- `reviewed`: `true`
- `style_consistency`: `pass`, `minor_deviation`, or `major_deviation`
- `score`: approximate 0-1 style consistency score
- `matched_traits`
- `deviations`
- `recommendation`: `use`, `revise_prompt`, or `regenerate`
- `suggested_revision`: prompt or parameter changes when needed

If there is no output image, no `style_id`, or the image cannot be inspected, set `reviewed: false`, `style_consistency: "not_reviewed"`, and explain why in `deviations`.

For `major_deviation`, do not silently accept the image as style-consistent. Show the user the visual review, explain the drift, and recommend revising the prompt or regenerating.

6. Validate and record the generation. Prefer the bundled script:

```bash
python skills/image-generate/scripts/record_generation.py --json <generation-run.json>
```

For retries, record every attempt and include retry metadata:

```bash
python skills/image-generate/scripts/record_generation.py --json <generation-run.json> --attempt 1 --max-attempts 3 --retryable true
python skills/image-generate/scripts/record_generation.py --json <generation-run.json> --attempt 2 --max-attempts 3 --retry-of <previous-generation-run-id>
```

The JSON should include:

- `source_prompt`
- `refined_prompt`
- `negative_prompt`
- `style_id`
- `generation_skill`
- `skill_params`, including the final `aspectRatio`
- `skill_result_meta`
- `visual_review`
- `outputs`: archived generated asset metadata
- `status`: `generated` or `failed`
- `error` when failed

7. Ask the user for feedback. Save feedback when provided:

```bash
PYTHONPATH=src python -m aether_core.cli generation feedback <run_id> --liked true --notes "<notes>"
```

## Rules

- This skill is the Aether workflow skill. The actual image-generation capability is selected by `generation.defaultGenerationSkill`.
- Do not drop `aspectRatio` between prompt refinement and generation. If a prompt record has `generation_params.aspectRatio`, use that over the config default.
- Always perform visual review for successful generations when an inspectable output image is available.
- Treat visual review as advisory. Do not automatically discard, overwrite, or regenerate an image without user confirmation.
- Do not record successful generations with unarchived output images. Archive first, then save the generation run.
- Do not use this skill directly for a raw, fuzzy, or short text prompt; switch to `prompt-refine` first and come back with a refined prompt or saved prompt record.
- For a prompt record created in the same conversation turn, confirm that the user approved the refined prompt before making a paid or external generation call, unless they explicitly opted into auto-generation after refinement.
- If the user provided image(s) as references and did not explicitly ask for a new generated image, switch to `style-capture` instead.
- If the user only asks to analyze, remember, store, deduplicate, or extract style from image(s), switch to `style-capture` instead.
- Do not store provider secrets in Aether config.
- Always record success or failure so the generation history remains auditable.
- Retry transient generation failures up to the configured maximum and record each attempt, including the final success or final failure.
