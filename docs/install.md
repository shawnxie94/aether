# Aether Installation And Sharing

## npm Installation

The recommended sharing path is an npm package. The npm package is only a distribution layer; it still contains a Codex marketplace with the Aether plugin inside.

After publishing, users can run:

```bash
npx aether-codex-plugin install
```

The command performs the installation explicitly:

- copies the bundled marketplace to `~/.aether/codex-marketplace/aether-codex-plugin`
- registers the marketplace with Codex
- initializes `~/.aether/data`
- writes `~/.config/aether/config.json`
- installs the `aether` CLI shim at `~/.local/bin/aether`

The package does not use npm `postinstall` to write into user directories.

After installation, restart Codex or open a new thread so plugin skills reload. If `aether doctor` is not found, add `~/.local/bin` to `PATH`.

## First Use In Codex

Start with natural language:

```text
Help me turn these references into reusable visual memory.
```

Expected result:

- Codex summarizes the reusable visual traits in normal language.
- Aether stores a pending confirmation batch.
- Codex asks whether to save the memory as new, attach it to an existing memory, save it as a variant, or ignore one-off details.

For text prompts:

```text
Refine "a lonely girl walking through a rainy future city" into a generation-ready prompt.
```

Expected result:

- Codex proposes a refined prompt.
- It lists key assumptions and image parameters.
- It asks for confirmation before generating images.

## Marketplace Path Only

If you only want to print the persistent marketplace path:

```bash
npx aether-codex-plugin marketplace-path
```

This also refreshes the persistent marketplace copy so Codex does not point to an `npx` temporary directory.

## Manual Codex Marketplace Installation

The repository itself is a Codex marketplace root. Its entry file is:

```text
.agents/plugins/marketplace.json
```

Share the full repository or published package rather than only `plugins/aether`. After receiving the full directory, run:

```bash
codex plugin marketplace add <aether-marketplace-root>
```

`<aether-marketplace-root>` must be the directory containing `.agents/plugins/marketplace.json`.

After installation, enable Aether in the Codex plugin UI and open a new thread.

If the marketplace already exists and the local directory was updated:

```bash
codex plugin marketplace upgrade aether
```

## Publishing To npm

From the repository root:

```bash
plugins/aether/scripts/package-plugin.sh
```

Output:

```text
dist/aether-codex-plugin-<version>.tgz
```

Check package contents before publishing:

```bash
npm pack --dry-run
```

Publish:

```bash
npm publish
```

If you switch to a scoped package such as `@your-scope/aether-codex-plugin`, first public publish needs:

```bash
npm publish --access public
```

## Local Development Cache Install

From the repository root:

```bash
plugins/aether/scripts/install-local.sh
```

The script:

- syncs `plugins/aether` to `~/.codex/plugins/cache/aether/aether/<version>`
- creates or migrates `~/.aether/codex-plugin/config.json`
- creates `~/.config/aether/config.json`
- installs `~/.local/bin/aether`
- initializes `~/.aether/data`

Existing user config is preserved. Missing fields are filled from the bundled defaults, and a `config.json.bak` backup is written before updates.

This path writes directly to the local Codex plugin cache. It is useful for development, but npm install is the recommended sharing path.

## CLI

```bash
aether doctor
aether config show
aether visual-asset list --summary
aether prompt compose --source-prompt "a lonely rainy neon city"
```

More examples: [cli.md](cli.md)

Development from the repository root can use:

```bash
PYTHONPATH=src python -m aether_core.cli doctor
```

## Data Locations

User config:

```text
~/.config/aether/config.json -> ~/.aether/codex-plugin/config.json
```

User data:

```text
~/.aether/data/aether.sqlite
~/.aether/data/assets
~/.aether/data/cache
~/.aether/data/runs
```

Plugin cache:

```text
~/.codex/plugins/cache/aether/aether/<version>
```
