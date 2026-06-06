# Aether Agent Guide

## Project Shape

- Repository root: `/Users/shawn/Documents/GitHub/aether`
- Main plugin package: `plugins/aether`
- Python package: `plugins/aether/src/aether_core`
- Codex plugin manifest: `plugins/aether/.codex-plugin/plugin.json`
- Skill entrypoints:
  - `plugins/aether/skills/aether-orchestrator`
  - `plugins/aether/skills/visual-memory`
  - `plugins/aether/skills/visual-asset-capture`
  - `plugins/aether/skills/prompt-refine`
  - `plugins/aether/skills/image-generate`

Aether is a Codex plugin for local visual asset memory, prompt refinement, image generation bookkeeping, asset archiving, and visual consistency review.

## Default Commands

Run commands from the repository root unless noted otherwise:

```bash
PYTHONPATH=src python -m aether_core.cli doctor
PYTHONPATH=src python -m unittest discover -s plugins/aether/tests
```

Useful validation commands:

```bash
python -m json.tool plugins/aether/schemas/visual-asset.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/visual-asset-candidate.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/prompt-record.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/generation-run.schema.json >/dev/null
node scripts/aether-plugin.js doctor
npm pack --dry-run
```

Before committing:

```bash
git diff --check
PYTHONPATH=src python -m unittest discover -s plugins/aether/tests
```

## Configuration And Data

Config lookup order is implemented in `aether_core.config`:

1. `~/.config/aether/config.json`
2. nearest workspace `config.json`
3. `.aether/config.json` in the current directory

On this machine, the active plugin config may be under `/Users/shawn/.aether/codex-plugin/config.json`. Do not assume the repo-local `plugins/aether/config.json` is the active runtime config without checking:

```bash
aether config show
```

Runtime data should stay outside the plugin install directory. Typical storage paths are:

- SQLite database: `~/.aether/data/aether.sqlite`
- reference assets: `~/.aether/data/assets/references`
- generated assets: `~/.aether/data/assets/generated`
- cache: `~/.aether/data/cache`

Do not delete or rewrite user data directories unless explicitly requested.

## Core Data Rules

- Visual assets live in SQLite `visual_assets`.
- Pending image-analysis modules live in SQLite `visual_asset_candidates`.
- Prompt records live in SQLite `prompt_records`.
- Generation records live in SQLite `generation_runs`.
- Image edits are also generation records with `mode: edit`, preserving source generation and source output lineage.
- Reference and generated image files are asset-managed.
- Successful generated image outputs must be archived through `aether_core.output_archiving` before recording generation runs.
- Prompt records should preserve `generation_params`, including `aspectRatio`.
- Generation records should preserve final `skill_params`, archived `outputs`, and `visual_review`.

## Skill Workflow Rules

- Use `visual-memory` only for listing or inspecting persisted visual assets, visual systems, recipes, candidates, generation history, evidence, quality stats, and local asset inventory.
- Use `visual-asset-capture` for reference images, screenshots, source-image prompts, or reusable visual asset sedimentation.
- Use `prompt-refine` before generation when the user gives a raw or fuzzy text prompt.
- Use `image-generate` after the user explicitly asks to generate/create/render/output a new image, or asks to edit an existing generated image.
- Do not call paid or external image generation before the user has confirmed a newly refined prompt unless they explicitly opted into auto-generation.
- Visual review is advisory. Do not automatically discard, overwrite, merge, or regenerate without user confirmation.

## Testing Expectations

Add focused tests when changing:

- storage schema or migration behavior
- CLI command behavior
- bundled skill scripts
- generated asset archiving
- prompt/generation parameter propagation
- visual review persistence
- chat attachment extraction

Prefer `unittest` because the repo currently uses the standard library test runner. `pytest` may not be installed.

## Installed Plugin Cache

The installed Codex plugin cache is separate from this repo, commonly:

`/Users/shawn/.codex/plugins/cache/aether/aether/<version>`

Source changes in this repo do not automatically update that cache. If the user asks for behavior that must be available immediately through `$aether:*` in the current Codex session, sync the specific changed files to the cache and verify there too. Keep source changes as the canonical implementation.

## Editing Notes

- Keep generated runtime data out of git.
- For current Visual Asset Memory work, backward compatibility with the old style workflow is not required unless the user explicitly asks for it.
- Preserve user intent in prompt refinement; do not replace the core subject, scene, action, mood, or explicit constraints.
- Keep provider-specific image generation details behind skill/config boundaries.
- Avoid large unrelated refactors when editing skill instructions or scripts.

## Layout Verification

Run the bundled verify script whenever a config / symlink / panel / "where do my
images live" question comes up. It checks:

- The global symlink `~/.config/aether/config.json` points to `~/.aether/codex-plugin/config.json`
- The global config has absolute storage paths (not the dev template)
- The runtime data directory and SQLite DB exist
- The running panel process is reading the global DB
- No stale `plugins/aether/.aether/` (project-local data) is left behind

```bash
bash scripts/verify_aether_layout.sh
```

If a future bug of the "panel does not see my new images" family recurs, run this
script first. The most common root cause is the global symlink having been
(re)pointed at `plugins/aether/config.json` (the dev template, with relative
paths) instead of the install-rewritten global config. Re-run
`plugins/aether/scripts/install-local.sh` to restore the canonical layout.

## Symlink Safety Check

`aether_core.config.find_config` now refuses to silently use a dev template
when the global symlink exists. The check fires when the resolved symlink
target has relative `storage.databasePath` (the dev template signature). The
runtime raises a clear error recommending `install-local.sh`, and dev users
can opt out with `AETHER_ALLOW_PROJECT_CONFIG=1`.

## Cache Sync Reminder

Source changes in `plugins/aether/src/aether_core/` are not auto-propagated to
the Codex plugin cache at `~/.codex/plugins/cache/aether/aether/<version>/`.
After editing source, run:

```bash
cp plugins/aether/src/aether_core/config.py \
   ~/.codex/plugins/cache/aether/aether/0.1.0/src/aether_core/config.py
rm -rf ~/.codex/plugins/cache/aether/aether/0.1.0/src/aether_core/__pycache__
```

…or the equivalent for any other source file. Then restart the panel from a
directory that does not itself contain a `config.json` (e.g. `/tmp`) so the
global symlink is the discovery path actually used.
