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

config = json.loads((plugin_root / "config.json").read_text(encoding="utf-8"))
data_root = aether_home / "data"
config["storage"] = {
    "databasePath": str(data_root / "aether.sqlite"),
    "assetRoot": str(data_root / "assets"),
    "referenceImageDir": str(data_root / "assets/references"),
    "generatedImageDir": str(data_root / "assets/generated"),
    "runDir": str(data_root / "runs"),
    "cacheDir": str(data_root / "cache"),
}
config_target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

ln -sfn "$config_target" "$config_link_dir/config.json"
ln -sfn "$cache_dir/scripts/aether" "$bin_dir/aether"

"$bin_dir/aether" init >/dev/null

cat <<EOF
Aether installed locally.
plugin_cache=$cache_dir
config=$config_link_dir/config.json
cli=$bin_dir/aether

Restart Codex to reload plugin skills.
EOF
