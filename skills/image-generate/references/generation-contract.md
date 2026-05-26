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
- `outputs`
- `status`
- `error`

Use `status: generated` after successful image creation.
Use `status: failed` and fill `error` if generation cannot run.

