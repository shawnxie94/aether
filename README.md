# Aether

Aether is a Codex plugin backed style memory and prompt refinement system for AI image generation.

The repository is a single-plugin Codex marketplace. The Aether plugin package lives in `plugins/aether`.

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
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli init
PYTHONPATH=src python -m aether_core.cli doctor
```

The project reads configuration from `~/.config/aether/config.json` first, then falls back to the nearest workspace `config.json`, then `.aether/config.json` in the current directory.

## CLI Examples

Create a style card:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli style create --json style-card.json
PYTHONPATH=src python -m aether_core.cli style create --json style-card.json --ingest-assets
```

Compare a new style profile against active styles:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli style compare --profile style-profile.json
```

Activate, archive, branch, or merge styles:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli style activate style_neon-melancholy
PYTHONPATH=src python -m aether_core.cli style archive style_neon-melancholy
PYTHONPATH=src python -m aether_core.cli style branch style_parent --json branch-style-card.json
PYTHONPATH=src python -m aether_core.cli style merge style_branch style_parent
```

Ingest a reference asset:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli asset ingest --path reference.png --kind reference
```

Render a prompt from a style template:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli prompt render --style-id style_neon-melancholy --source-prompt "a lonely girl in a future city"
```

Save a refined prompt:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli prompt save --json prompt-record.json
```

Record a generation:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli generation record --json generation-run.json
```

Validate JSON before saving:

```bash
cd plugins/aether
PYTHONPATH=src python -m aether_core.cli validate style --json style-card.json
PYTHONPATH=src python -m aether_core.cli validate prompt --json prompt-record.json
PYTHONPATH=src python -m aether_core.cli validate generation --json generation-run.json
```

## Codex Plugin

Marketplace metadata lives in `.agents/plugins/marketplace.json`.

Plugin metadata lives in `plugins/aether/.codex-plugin/plugin.json`.

Skills live in:

- `plugins/aether/skills/aether-orchestrator`
- `plugins/aether/skills/style-capture`
- `plugins/aether/skills/prompt-refine`
- `plugins/aether/skills/image-generate`

The plugin reads project configuration from the workspace `config.json`; it does not store project data in the plugin install directory.

## Schemas And Examples

JSON schemas live in `plugins/aether/schemas/`:

- `plugins/aether/schemas/config.schema.json`
- `plugins/aether/schemas/style-card.schema.json`
- `plugins/aether/schemas/prompt-record.schema.json`
- `plugins/aether/schemas/generation-run.schema.json`

Example payloads live in `plugins/aether/examples/`:

- `plugins/aether/examples/style-card.json`
- `plugins/aether/examples/prompt-record.json`
- `plugins/aether/examples/generation-run.json`

The SQLite database records schema version in `schema_migrations`.
