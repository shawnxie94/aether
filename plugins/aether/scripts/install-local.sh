#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
plugin_root="$(cd "$script_dir/.." >/dev/null 2>&1 && pwd)"

version="$("${PYTHON:-python3}" - "$plugin_root/.codex-plugin/plugin.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
)"

codex_home="${CODEX_HOME:-$HOME/.codex}"
aether_home="${AETHER_HOME:-$HOME/.aether}"
cache_dir="${AETHER_CACHE_DIR:-$codex_home/plugins/cache/aether/aether/$version}"
bin_dir="${AETHER_BIN_DIR:-$HOME/.local/bin}"
config_link_dir="${AETHER_CONFIG_DIR:-$HOME/.config/aether}"
config_target="$aether_home/codex-plugin/config.json"

rm -rf "$cache_dir"
mkdir -p "$cache_dir" "$bin_dir" "$config_link_dir" "$(dirname "$config_target")"

"${PYTHON:-python3}" - "$plugin_root" "$cache_dir" "$config_target" "$aether_home" <<'PY'
import json
import shutil
import sys
from pathlib import Path

plugin_root = Path(sys.argv[1])
cache_dir = Path(sys.argv[2])
config_target = Path(sys.argv[3])
aether_home = Path(sys.argv[4]).expanduser()

ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".aether", "dist")
shutil.copytree(plugin_root, cache_dir, dirs_exist_ok=True, ignore=ignore)

default_config = json.loads((plugin_root / "config.json").read_text(encoding="utf-8"))
data_root = aether_home / "data"
default_config["storage"] = {
    "databasePath": str(data_root / "aether.sqlite"),
    "assetRoot": str(data_root / "assets"),
    "referenceImageDir": str(data_root / "assets/references"),
    "generatedImageDir": str(data_root / "assets/generated"),
    "runDir": str(data_root / "runs"),
    "cacheDir": str(data_root / "cache"),
}


def merge_defaults(default, existing):
    if isinstance(default, dict) and isinstance(existing, dict):
        merged = dict(existing)
        for key, default_value in default.items():
            if key in merged:
                merged[key] = merge_defaults(default_value, merged[key])
            else:
                merged[key] = default_value
        return merged
    return existing


if config_target.exists():
    backup_path = config_target.with_suffix(config_target.suffix + ".bak")
    shutil.copy2(config_target, backup_path)
    existing_config = json.loads(config_target.read_text(encoding="utf-8"))
    config = merge_defaults(default_config, existing_config)
else:
    config = default_config

config_target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

ln -sfn "$config_target" "$config_link_dir/config.json"
ln -sfn "$cache_dir/scripts/aether" "$bin_dir/aether"

AETHER_CONFIG_PATH="$config_target" "$bin_dir/aether" init >/dev/null

cat <<EOF
Aether installed locally.
plugin_cache=$cache_dir
config=$config_link_dir/config.json
cli=$bin_dir/aether

Restart Codex to reload plugin skills.
EOF

# Post-install health check. The project layout script lives next to the
# aether repo root; from here ($plugin_root is <project>/plugins/aether)
# it is one level up under scripts/.
project_root="$(cd "$plugin_root/.." >/dev/null 2>&1 && pwd)"
verify_script="$project_root/scripts/verify_aether_layout.sh"
if [ -x "$verify_script" ]; then
  printf "\n=== Post-install layout verification ===\n"
  if "$verify_script" --project-root "$project_root"; then
    :
  else
    printf "warning: Aether installed but verify_aether_layout.sh reported drift.\n" >&2
    printf "         Investigate the items above before relying on the install.\n" >&2
  fi
else
  printf "note: verify_aether_layout.sh not found at %s; skipping post-install check.\n" "$verify_script" >&2
fi
