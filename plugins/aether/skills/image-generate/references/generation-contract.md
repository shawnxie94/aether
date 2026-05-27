# Generation Contract

The Aether image-generate skill records the generation workflow. The actual image-generation capability is selected by `generation.defaultGenerationSkill` in `config.json`.

## Required Record Fields

- `refined_prompt`
- `generation_skill`

## Recommended Record Fields

- `mode`: `generate` for first-pass generation, `edit` for image edits
- `source_generation_id`: parent generation run when editing an existing output
- `source_output_asset_id`: archived generated asset id being edited
- `edit_instruction`: concrete edit request for `mode: edit`
- `edit_regions`: local regions or defect descriptions for targeted edits
- `source_prompt`
- `negative_prompt`
- `selected_assets`
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

After successful generation, compare each output image against the selected visual assets when they are available.

`visual_review` should include:

- `reviewed`: boolean
- `style_consistency`: `pass`, `minor_deviation`, `major_deviation`, or `not_reviewed`
- `score`: approximate 0-1 style consistency score
- `matched_traits`: reusable visual traits that are present
- `deviations`: visual traits that drifted from the selected assets or reference images
- `recommendation`: `use`, `edit`, `revise_prompt`, or `regenerate`
- `suggested_revision`: concise prompt or parameter adjustment when revision is recommended
- `suggested_edit_instruction`: concise image-edit instruction when only local regions need correction
- `localized_deviations`: local defects that can likely be fixed with image editing

Use `major_deviation` when the output does not preserve the selected assets' core art direction, color/lighting language, composition rules, mood, scene logic, or material/rendering treatment.
Use `recommendation: edit` when the overall image is acceptable but one or more local regions are flawed, such as hands, text, face details, object geometry, a localized style break, or small composition cleanup.
