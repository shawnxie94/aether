# Contributing

Thanks for improving Aether.

## Development Setup

Run from the repository root:

```bash
npm test
npm pack --dry-run
```

For local plugin testing:

```bash
plugins/aether/scripts/install-local.sh
```

Restart Codex or open a new thread after reinstalling the plugin.

## Guidelines

- Keep user-facing flows natural-language-first. Do not expose raw JSON, internal IDs, or storage schema details unless the user asks for low-level details.
- Keep persisted reusable semantic fields in English so visual memory remains portable across user languages.
- Preserve user-provided source prompts, quoted text, proper nouns, and notes in their original language.
- Ask for confirmation before image generation, irreversible merges, or long-term memory confirmation.
- Add focused `unittest` coverage when changing storage, CLI behavior, bundled scripts, or skill workflows.
- Edit skill files at `plugins/aether/skills/<skill>/SKILL.md`, not the Codex plugin cache at `~/.codex/plugins/cache/aether/aether/<version>/skills/<skill>/`. The cache is rebuilt from the source by `make install-local`; cache-only edits are silently lost on the next reinstall. See `docs/skill-source-vs-install-cache.md` for the full path, verification one-liner, and recovery steps.

## Release Checks

```bash
npm test
node scripts/aether-plugin.js doctor
npm pack --dry-run
plugins/aether/scripts/package-plugin.sh
```
