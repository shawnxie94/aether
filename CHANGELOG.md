# Changelog

## Unreleased

- Add recipe-level `must_cover_ratios` and `signature_self_check` composition rule keys. Recipes can now carry explicit visual signal budgets and self-check anchors; the composer reads them and appends a dedicated "Recipe signature coverage:" paragraph near the end of `refined_prompt` so the numbers survive prompt word-frequency dilution.
- Split `visual_review` into three independent consistency fields: `style_consistency` (overall), `recipe_fidelity` (recipe signature), and `subject_consistency` (subject identity). Each field accepts the same `high` / `moderate` / `low` / `major_deviation` / `not_reviewed` scale; the legacy `pass` / `minor_deviation` values are still accepted by the validator and are normalized to `high` / `moderate` inside storage so historical reviews keep their meaning.
- `suggest_generation_reuse` now requires `recipe_fidelity` to pass before a generation run auto-promotes a new recipe candidate, so a visually pleasing but recipe-drifted image is no longer silently turned into a recipe.
- `visual_asset_quality` exposes a `fidelity` and `subject_consistency` score breakdown so consumers can see whether an asset is producing strong recipe matches, strong subject matches, or both.
- New validation, composer, and storage tests cover the new rule keys, the new visual_review fields, legacy value normalization, and the signature coverage paragraph rendering.

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
