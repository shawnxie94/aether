# Changelog

## Unreleased

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
