# Changelog

## Unreleased

- `output_archiving.resolve_generation_relations` now bridges `recipe_id` / `visual_system_id` / `subject_asset_id` into `generation_runs.selected_assets` so the panel and evidence layer see references that previously lived only on the relation joins. Old selection order is preserved; new ids are appended in recipe → system → subject order and de-duplicated. This also lands the missing `resolve_generation_relations` implementation that `cli.py` already imported on HEAD.
- `create_generation_run` persists `recipe_id`, `visual_system_id`, and `subject_asset_id` on the `generation_runs` row, with `_ensure_column` lazily adding the columns on legacy databases so existing `aether.sqlite` files keep working without a migration step. `style_id` is no longer hard-set to `None`. SELECT tolerates older rows that predate the columns.
- `create_visual_asset` now normalizes `source_references[]` before writing, aliasing the legacy `id` key to `asset_id` and `path` to `image_path` when the canonical keys are absent. Historical entries from `save_candidate_batch` and the original Codex sedimentation agent used `id` / `path`, which the panel silently dropped, so every recent visual asset card rendered as "No linked image" with `0 ref / 0 gen`. New entries carry the canonical keys, the legacy `path` is preserved as `original_image_path` for provenance lookups, and a one-time backfill normalized 45 historical rows (all 482 references now resolve). Two new storage tests cover the normalizer and the create-path aliasing.

- Add recipe-level `must_cover_ratios` and `signature_self_check` composition rule keys. Recipes can now carry explicit visual signal budgets and self-check anchors; the composer reads them and appends a dedicated "Recipe signature coverage:" paragraph near the end of `refined_prompt` so the numbers survive prompt word-frequency dilution.
- Split `visual_review` into three independent consistency fields: `style_consistency` (overall), `recipe_fidelity` (recipe signature), and `subject_consistency` (subject identity). Each field accepts the same `high` / `moderate` / `low` / `major_deviation` / `not_reviewed` scale; the legacy `pass` / `minor_deviation` values are still accepted by the validator and are normalized to `high` / `moderate` inside storage so historical reviews keep their meaning.
- `suggest_generation_reuse` now requires `recipe_fidelity` to pass before a generation run auto-promotes a new recipe candidate, so a visually pleasing but recipe-drifted image is no longer silently turned into a recipe.
- `visual_asset_quality` exposes a `fidelity` and `subject_consistency` score breakdown so consumers can see whether an asset is producing strong recipe matches, strong subject matches, or both.
- New validation, composer, and storage tests cover the new rule keys, the new visual_review fields, legacy value normalization, and the signature coverage paragraph rendering. All 136 tests pass.

### Follow-up: prompt-refine workflow roundtrip

- Expose the recipe signature coverage paragraph as a structured `composition_plan.signature_coverage` field with `blocks` (raw rules) and `paragraph` (rendered text) so callers no longer have to substring-search `refined_prompt`. The composer writes the same paragraph into `refined_prompt` as before, so the model still sees the signature coverage block; the structured field is for tooling.
- When the caller passes an explicit `recipe_ids` list, treat that recipe as the primary style contract: any selected asset whose type overlaps a core asset of the recipe is recorded as a `recipe_primary_style` conflict in `composition_plan.conflicts`, with `severity` set to `demoted` for implicit assets or `explicit_override` for explicit-but-overlapping ones. The recipe's core asset is never silently dropped; the conflict entry carries a resolution hint so the caller can decide.
- `record_generation.py` now writes an auditable `visual_review` placeholder on failed runs (with the infra error carried in `deviations`) so retry history is inspectable.
- `record_generation.py` accepts a `--workspace-mirror` flag that creates stable symlinks under `<cwd>/outputs/aether-mirror/<run_id>/` to each archived output, so the workspace always has a quick-open path to the latest generated image.
- New `aether recipe update <recipe_id>` CLI supports `--append-composition-rule`, `--append-prompt-fragment-by-asset`, `--metadata-patch`, and `--reason` for targeted recipe edits that keep validation intact. Storage gains `update_recipe` and `update_visual_asset_prompt_fragments` helpers; both run full validation and write a recipe revision entry.
- Recipe schema enum now lists `must_cover_ratios` and `signature_self_check`; new `plugins/aether/examples/recipe-with-signature-coverage.json` example; `visual-asset-capture` SKILL.md has a new "When To Add Recipe Signature Coverage Rules" section.
- New validation, composer, and storage tests cover the structured signature coverage field, the recipe-dominance conflict path, the failure-path visual review placeholder, and the new storage helpers. All 142 tests pass.

- Sync the panel URL hash with the active view, search / type / status filters, and any open detail. Refreshing the page now lands the user on the same screen instead of bouncing back to the default landing page, and tab / detail navigation becomes undoable with the browser back button while filter keystrokes still use ``replaceState`` to keep the history stack clean.
- Document an idempotency check in `visual-asset-capture`: `aether visual-asset candidates confirm-batch` already persists recipe / visual_system candidates in the same batch, so a follow-up `aether recipe candidates confirm` or `aether visual-system candidates confirm` against the same candidate ids would create `-2` duplicates. The skill now warns explicitly and tells Codex to re-check `candidates get` before re-confirming, and to use `recipe merge` / `visual-system merge` to clean up a duplicate if one was already created.

## 0.1.0

- Publish Aether's public README experience with bilingual documentation and visual examples.
- Package README assets, installation docs, CLI docs, license, and contribution guide for npm users.
- Improve CLI help, installer diagnostics, and user-facing Aether workflow messages.

## 0.0.5

- Package Aether as a Codex marketplace npm distribution.
- Add local install flow for Codex plugin cache, user config, and CLI shim.
- Add visual memory, prompt refinement, generation recording, and asset governance commands.
- Add natural-language-first documentation for broader sharing.
