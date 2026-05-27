# Aether

Aether is a Codex plugin backed visual asset memory and prompt refinement system for AI image generation.

The repository is a single-plugin Codex marketplace. The Aether plugin package lives in `plugins/aether`.

It keeps model reasoning inside Codex and uses the local project core for deterministic work:

- config discovery
- local SQLite storage
- visual asset memory
- visual asset library browsing
- prompt refinement records
- generation run records
- Codex plugin and skill entrypoints

## Quick Start

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli init
PYTHONPATH=src python -m aether_core.cli doctor
```

The project reads configuration from `~/.config/aether/config.json` first, then falls back to the nearest workspace `config.json`, then `.aether/config.json` in the current directory.

## CLI Examples

Create and inspect reusable visual assets:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli visual-asset create --json visual-asset.json
PYTHONPATH=src python -m aether_core.cli visual-asset list --type lighting --summary
PYTHONPATH=src python -m aether_core.cli visual-asset get visual_asset_lighting-rainy-neon-reflection
```

Persist image-analysis candidate assets and confirm them:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli visual-asset candidates create --json visual-asset-candidates.json
PYTHONPATH=src python -m aether_core.cli visual-asset candidates list --status pending --summary
PYTHONPATH=src python -m aether_core.cli visual-asset candidates decide asset_candidate_example new_asset
PYTHONPATH=src python -m aether_core.cli visual-asset candidates decide asset_candidate_example asset_variant --target-asset-id visual_asset_parent
PYTHONPATH=src python -m aether_core.cli visual-asset candidates decide asset_candidate_example existing_asset --target-asset-id visual_asset_existing
PYTHONPATH=src python -m aether_core.cli visual-asset candidates decide asset_candidate_example ignore
```

Activate, archive, branch, or merge visual assets:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli visual-asset activate visual_asset_lighting-rainy-neon-reflection
PYTHONPATH=src python -m aether_core.cli visual-asset archive visual_asset_lighting-rainy-neon-reflection
PYTHONPATH=src python -m aether_core.cli visual-asset branch visual_asset_parent --json visual-asset-variant.json
PYTHONPATH=src python -m aether_core.cli visual-asset merge visual_asset_branch visual_asset_parent
```

Ingest a reference asset:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli asset ingest --path reference.png --kind reference
```

Inspect local assets:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli asset list --kind generated
PYTHONPATH=src python -m aether_core.cli asset stats
PYTHONPATH=src python -m aether_core.cli asset duplicates --kind generated
PYTHONPATH=src python -m aether_core.cli asset unreferenced --kind generated
```

Save a refined prompt:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli prompt compose --source-prompt "a lonely girl in a future city" --query "rain neon" --save
PYTHONPATH=src python -m aether_core.cli prompt save --json prompt-record.json
```

Prompt records include `generation_params`, so prompt refinement can recommend an image `aspectRatio` and image generation can carry that value into `skill_params`.
Prompt composition records also include `selected_assets`, `composition_plan`, and `conflicts`.

Record a generation:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli generation record --json generation-run.json
```

Generation records include `visual_review` so Aether can capture post-generation consistency checks and recommend prompt revision or regeneration when the generated image drifts from the selected visual assets.
Successful generation records also archive generated image files into `generatedImageDir` and store archived asset metadata in `outputs`.

Review generation history:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli generation list
PYTHONPATH=src python -m aether_core.cli generation list --asset-id visual_asset_lighting-rainy-neon-reflection
PYTHONPATH=src python -m aether_core.cli generation get generation_example
PYTHONPATH=src python -m aether_core.cli generation stats
```

Inspect asset evidence and generated quality feedback:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli visual-asset evidence visual_asset_lighting-rainy-neon-reflection
PYTHONPATH=src python -m aether_core.cli visual-asset quality visual_asset_lighting-rainy-neon-reflection
```

Validate JSON before saving:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli validate visual-asset --json visual-asset.json
PYTHONPATH=src python -m aether_core.cli validate prompt --json prompt-record.json
PYTHONPATH=src python -m aether_core.cli validate generation --json generation-run.json
```

## Codex Plugin

Marketplace metadata lives in `.agents/plugins/marketplace.json`.

Plugin metadata lives in `plugins/aether/.codex-plugin/plugin.json`.

Skills live in:

- `plugins/aether/skills/aether-orchestrator`
- `plugins/aether/skills/style-library`
- `plugins/aether/skills/style-capture`
- `plugins/aether/skills/prompt-refine`
- `plugins/aether/skills/image-generate`

The plugin reads project configuration from the workspace `config.json`; it does not store project data in the plugin install directory.

## Schemas And Examples

JSON schemas live in `plugins/aether/schemas/`:

- `plugins/aether/schemas/config.schema.json`
- `plugins/aether/schemas/visual-asset.schema.json`
- `plugins/aether/schemas/visual-asset-candidate.schema.json`
- `plugins/aether/schemas/prompt-record.schema.json`
- `plugins/aether/schemas/generation-run.schema.json`

Example payloads live in `plugins/aether/examples/`:

- `plugins/aether/examples/visual-asset.json`
- `plugins/aether/examples/visual-asset-candidates.json`
- `plugins/aether/examples/prompt-record.json`
- `plugins/aether/examples/generation-run.json`

The SQLite database records schema version in `schema_migrations`.
