# AGENTS.md — Aether Plugin Source

Scope: everything under `plugins/aether/`.

## Skill files

`SKILL.md` files under `plugins/aether/skills/<skill>/` are the
single source of truth. The matching files under
`~/.codex/plugins/cache/aether/aether/<version>/skills/<skill>/` are
a build artifact rebuilt by `make install-local` via
`plugins/aether/scripts/install-local.sh` (`shutil.copytree`). Always
edit the source, never the cache. After editing, run `make install-local`
and restart Codex (or open a new thread) so the running skill loader
picks up the new copy.

See `docs/skill-source-vs-install-cache.md` for the full reasoning,
recovery steps, and the verification `git status` one-liner.

## Confirmation gates

`SKILL.md` files in this directory contain explicit `⚠️ HARD GATE —
STOP HERE` blocks (in `visual-asset-capture`, `image-generate`, and
`aether-orchestrator`). Those gates enumerate irreversible commands
that must not be run before the user has answered the surrounding
confirmation step. Treat those blocks as hard rules, not prose.
