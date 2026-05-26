# Aether

Aether is a Codex plugin backed style memory and prompt refinement system for AI image generation.

It keeps model reasoning inside Codex and uses the local project core for deterministic work:

- config discovery
- local SQLite storage
- style cards
- style similarity scoring
- prompt refinement records
- generation run records
- Codex plugin and skill entrypoints

## Quick Start

```bash
PYTHONPATH=src python -m aether_core.cli init
PYTHONPATH=src python -m aether_core.cli doctor
```

The project reads configuration from `config.json` by default. Set `AETHER_CONFIG_PATH` to override.

## CLI Examples

Create a style card:

```bash
PYTHONPATH=src python -m aether_core.cli style create --json style-card.json
PYTHONPATH=src python -m aether_core.cli style create --json style-card.json --ingest-assets
```

Compare a new style profile against active styles:

```bash
PYTHONPATH=src python -m aether_core.cli style compare --profile style-profile.json
```

Activate, archive, branch, or merge styles:

```bash
PYTHONPATH=src python -m aether_core.cli style activate style_neon-melancholy
PYTHONPATH=src python -m aether_core.cli style archive style_neon-melancholy
PYTHONPATH=src python -m aether_core.cli style branch style_parent --json branch-style-card.json
PYTHONPATH=src python -m aether_core.cli style merge style_branch style_parent
```

Ingest a reference asset:

```bash
PYTHONPATH=src python -m aether_core.cli asset ingest --path reference.png --kind reference
```

Render a prompt from a style template:

```bash
PYTHONPATH=src python -m aether_core.cli prompt render --style-id style_neon-melancholy --source-prompt "a lonely girl in a future city"
```

Save a refined prompt:

```bash
PYTHONPATH=src python -m aether_core.cli prompt save --json prompt-record.json
```

Record a generation:

```bash
PYTHONPATH=src python -m aether_core.cli generation record --json generation-run.json
```

Validate JSON before saving:

```bash
PYTHONPATH=src python -m aether_core.cli validate style --json style-card.json
PYTHONPATH=src python -m aether_core.cli validate prompt --json prompt-record.json
PYTHONPATH=src python -m aether_core.cli validate generation --json generation-run.json
```

## Codex Plugin

Plugin metadata lives in `.codex-plugin/plugin.json`.

Skills live in:

- `skills/style-capture`
- `skills/prompt-refine`
- `skills/image-generate`

The plugin reads project configuration from the workspace `config.json`; it does not store project data in the plugin install directory.

## Schemas And Examples

JSON schemas live in `schemas/`:

- `schemas/config.schema.json`
- `schemas/style-card.schema.json`
- `schemas/prompt-record.schema.json`
- `schemas/generation-run.schema.json`

Example payloads live in `examples/`:

- `examples/style-card.json`
- `examples/prompt-record.json`
- `examples/generation-run.json`

The SQLite database records schema version in `schema_migrations`.
