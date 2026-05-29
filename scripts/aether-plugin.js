#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const packageRoot = path.resolve(__dirname, "..");
const pluginRoot = path.join(packageRoot, "plugins", "aether");
const marketplacePath = path.join(packageRoot, ".agents", "plugins", "marketplace.json");
const localInstallScript = path.join(pluginRoot, "scripts", "install-local.sh");
const persistentMarketplaceRoot = path.join(
  process.env.AETHER_MARKETPLACE_ROOT || path.join(os.homedir(), ".aether", "codex-marketplace"),
  "aether-codex-plugin"
);
const defaultCliPath = path.join(os.homedir(), ".local", "bin", "aether");
const defaultConfigPath = path.join(os.homedir(), ".config", "aether", "config.json");
const codexConfigPath = path.join(os.homedir(), ".codex", "config.toml");

function usage() {
  console.log(`Aether Codex plugin installer

Usage:
  aether-codex-plugin install [--skip-marketplace] [--skip-local]
  aether-codex-plugin doctor
  aether-codex-plugin marketplace-path

Commands:
  install            Register the bundled Codex marketplace and initialize local Aether CLI/config.
  doctor             Check packaged files and common local prerequisites.
  marketplace-path   Print the persistent marketplace path used for Codex registration.
`);
}

function hasFlag(args, flag) {
  return args.includes(flag);
}

function ensurePath(targetPath, label) {
  if (!fs.existsSync(targetPath)) {
    console.error(`Missing ${label}: ${targetPath}`);
    process.exit(1);
  }
}

function copyPath(source, target) {
  fs.cpSync(source, target, {
    recursive: true,
    force: true,
    dereference: false,
    filter: (item) => {
      const base = path.basename(item);
      return ![
        ".git",
        ".aether",
        "dist",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
      ].includes(base) && !base.endsWith(".pyc");
    },
  });
}

function preparePersistentMarketplace() {
  ensurePath(marketplacePath, "Codex marketplace manifest");
  ensurePath(path.join(pluginRoot, ".codex-plugin", "plugin.json"), "Codex plugin manifest");

  fs.rmSync(persistentMarketplaceRoot, { recursive: true, force: true });
  fs.mkdirSync(path.join(persistentMarketplaceRoot, "plugins"), { recursive: true });

  copyPath(path.join(packageRoot, ".agents"), path.join(persistentMarketplaceRoot, ".agents"));
  copyPath(pluginRoot, path.join(persistentMarketplaceRoot, "plugins", "aether"));

  if (fs.existsSync(path.join(packageRoot, "docs"))) {
    copyPath(path.join(packageRoot, "docs"), path.join(persistentMarketplaceRoot, "docs"));
  }

  for (const filename of ["README.md", "README.en.md", "AGENT.md", "package.json", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md"]) {
    const source = path.join(packageRoot, filename);
    if (fs.existsSync(source)) {
      fs.copyFileSync(source, path.join(persistentMarketplaceRoot, filename));
    }
  }

  const rootSrc = path.join(persistentMarketplaceRoot, "src");
  try {
    fs.symlinkSync("plugins/aether/src", rootSrc);
  } catch (error) {
    if (error.code !== "EEXIST") {
      copyPath(path.join(pluginRoot, "src"), rootSrc);
    }
  }

  return persistentMarketplaceRoot;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: packageRoot,
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) {
    if (!options.allowFailure) {
      console.error(`Failed to run ${command}: ${result.error.message}`);
      process.exit(1);
    }
    return false;
  }
  if (result.status !== 0) {
    if (!options.allowFailure) {
      process.exit(result.status || 1);
    }
    return false;
  }
  return true;
}

function doctor() {
  const checks = {
    package: {
      marketplaceManifest: fs.existsSync(marketplacePath),
      pluginManifest: fs.existsSync(path.join(pluginRoot, ".codex-plugin", "plugin.json")),
      localInstallScript: fs.existsSync(localInstallScript),
      docsPackaged: fs.existsSync(path.join(packageRoot, "docs", "install.md")),
      licensePackaged: fs.existsSync(path.join(packageRoot, "LICENSE")),
    },
    install: {
      persistentMarketplaceRoot,
      persistentMarketplaceExists: fs.existsSync(persistentMarketplaceRoot),
      cliPath: defaultCliPath,
      cliExists: fs.existsSync(defaultCliPath),
      configPath: defaultConfigPath,
      configExists: fs.existsSync(defaultConfigPath),
      codexConfigPath,
      codexConfigExists: fs.existsSync(codexConfigPath),
    },
    runtime: {},
  };
  for (const [name, args] of [
    ["python3", ["--version"]],
    ["codex", ["--version"]],
  ]) {
    const result = spawnSync(name, args, {
      cwd: packageRoot,
      env: process.env,
      stdio: "pipe",
      encoding: "utf8",
    });
    checks.runtime[name] = {
      available: !result.error && result.status === 0,
      output: (result.stdout || result.stderr || "").trim(),
    };
  }
  const codexConfig = fs.existsSync(codexConfigPath) ? fs.readFileSync(codexConfigPath, "utf8") : "";
  checks.install.marketplaceRegistered = codexConfig.includes("[marketplaces.aether]")
    && codexConfig.includes(persistentMarketplaceRoot);
  ensurePath(marketplacePath, "Codex marketplace manifest");
  ensurePath(path.join(pluginRoot, ".codex-plugin", "plugin.json"), "Codex plugin manifest");
  ensurePath(localInstallScript, "local install script");
  console.log(JSON.stringify(
    {
      ok: true,
      packageRoot,
      persistentMarketplaceRoot,
      sourceMarketplaceRoot: packageRoot,
      marketplacePath,
      pluginRoot,
      checks,
    },
    null,
    2
  ));
}

function install(args) {
  doctor();
  const marketplaceRoot = preparePersistentMarketplace();
  const persistentInstallScript = path.join(marketplaceRoot, "plugins", "aether", "scripts", "install-local.sh");

  if (!hasFlag(args, "--skip-local")) {
    run("bash", [persistentInstallScript]);
  }

  if (!hasFlag(args, "--skip-marketplace")) {
    const added = run("codex", ["plugin", "marketplace", "add", marketplaceRoot], { allowFailure: true });
    if (!added) {
      console.error("codex marketplace add failed; trying marketplace upgrade for existing marketplace 'aether'.");
      const upgraded = run("codex", ["plugin", "marketplace", "upgrade", "aether"], { allowFailure: true });
      if (!upgraded) {
        console.error(`Could not register the marketplace automatically. Manual command:
codex plugin marketplace add ${marketplaceRoot}`);
        process.exit(1);
      }
    }
  }

  console.log(`
Aether plugin installation finished.
Restart Codex or open a new thread so plugin skills reload.
If the aether command is not on your PATH yet, add ~/.local/bin.
`);
}

function main() {
  const [command = "help", ...args] = process.argv.slice(2);
  if (command === "help" || command === "--help" || command === "-h") {
    usage();
  } else if (command === "doctor") {
    doctor();
  } else if (command === "marketplace-path") {
    console.log(preparePersistentMarketplace());
  } else if (command === "install") {
    install(args);
  } else {
    console.error(`Unknown command: ${command}`);
    usage();
    process.exit(1);
  }
}

main();
