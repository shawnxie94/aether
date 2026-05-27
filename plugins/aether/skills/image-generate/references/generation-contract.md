# Generation Contract

The Aether image-generate skill records the generation workflow. The actual image-generation capability is selected by `generation.defaultGenerationSkill` in `config.json`.

## Required Record Fields

- `refined_prompt`
- `generation_skill`

## Recommended Record Fields

- `source_prompt`
- `negative_prompt`
- `style_id`
- `skill_params`
- `skill_result_meta`
- `visual_review`
- `outputs`
- `status`
- `error`

Use `status: generated` after successful image creation.
Use `status: failed` and fill `error` if generation cannot run.

## Output Archiving

Successful generation runs must archive every generated image into `generation.generatedImageDir` before the run is saved.

The recorder accepts outputs as:

- local file paths
- image URLs
- `data:image/*;base64,...` URLs
- objects containing `asset_path`, `image_path`, `file_path`, `path`, or `url`

Saved `outputs` should contain archived generated asset metadata, including `asset_id`, `asset_path`, `image_path`, `sha256`, `mime_type`, `size_bytes`, and `original_output`.

Failed generation runs may have an empty `outputs` array.

## Visual Review

After successful generation, compare each output image against the selected style card when `style_id` is available.

`visual_review` should include:

- `reviewed`: boolean
- `style_consistency`: `pass`, `minor_deviation`, `major_deviation`, or `not_reviewed`
- `score`: approximate 0-1 style consistency score
- `matched_traits`: reusable style traits that are present
- `deviations`: style traits that drifted from the style card or reference images
- `recommendation`: `use`, `revise_prompt`, or `regenerate`
- `suggested_revision`: concise prompt or parameter adjustment when revision is recommended

Use `major_deviation` when the output does not preserve the style's core art direction, color/lighting language, composition rules, or material/rendering treatment.
