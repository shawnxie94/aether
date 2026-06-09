# Aether Skill Source vs Install Cache

When you are about to edit a `SKILL.md` file, **always edit the file in
this repository, never the file in the Codex plugin cache.** This page
explains why, how to find the right path, and how to make your edits
take effect.

## Why

The Aether plugin is published as a Codex plugin. The Codex runtime
loads skills from a per-version cache directory, not directly from the
source tree:

| Layer | Path | Versioned? | Edited directly? |
| --- | --- | --- | --- |
| Source of truth (this repo) | `plugins/aether/skills/<skill>/SKILL.md` | yes, git-tracked | yes |
| Installed plugin cache | `~/.codex/plugins/cache/aether/aether/<version>/skills/<skill>/SKILL.md` | one copy per plugin version, replaced on reinstall | **no** |

`plugins/aether/scripts/install-local.sh` does
`shutil.copytree(plugin_root, cache_dir, ...)`, so the cache is a
**build artifact** rebuilt from the source on every `make install-local`
(or `bash plugins/aether/scripts/install-local.sh`). Editing the cache
copy is silently lost the next time someone reinstalls the plugin,
produces two copies of the same skill with different content, and is
**not** captured by `git status`.

## How To Find The Right Path

- The source path is always under `plugins/aether/skills/<skill>/` in
  this repository, where `<skill>` is one of:
  - `aether-orchestrator`
  - `visual-asset-capture`
  - `visual-memory`
  - `prompt-refine`
  - `image-generate`
- The cache path is `~/.codex/plugins/cache/aether/aether/<version>/skills/<skill>/`,
  where `<version>` matches `plugins/aether/.codex-plugin/plugin.json`.
- If you opened a SKILL file from a Codex tool suggestion, it is most
  likely the cache copy. Translate the path back to
  `plugins/aether/skills/<skill>/SKILL.md` before editing.

## After Editing

To make a SKILL change take effect in a running Codex:

1. Edit `plugins/aether/skills/<skill>/SKILL.md` (and any related files
   under that skill directory).
2. Reinstall the plugin so the cache is rebuilt:
   ```bash
   make install-local
   ```
3. Restart Codex or open a new thread so the skill loader picks up the
   new cache copy. Codex reads skills from the cache at thread start.

## How To Verify You Are Editing The Source

Before saving, run from the repository root:

```bash
git status -- plugins/aether/skills/
```

If your edit shows up there, you are editing the source. If
`git status` is silent but you still see the change locally, you are
almost certainly editing a cache copy — translate the path back and
redo the edit in the source tree.

## How To Recover From A Cache Edit

If you already edited a file under `~/.codex/plugins/cache/aether/...`:

1. Reapply the same change to `plugins/aether/skills/<skill>/SKILL.md`
   in this repository.
2. Run `make install-local` to refresh the cache.
3. Optionally `git diff` the source to confirm the change is captured
   before reinstalling.

Do **not** commit the cache directory. It is intentionally outside the
source tree and contains a per-version copy that would be overwritten
on the next reinstall.
