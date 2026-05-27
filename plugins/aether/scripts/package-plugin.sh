#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C
export LANG=C

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
plugin_root="$(cd "$script_dir/.." >/dev/null 2>&1 && pwd)"
repo_root="$(cd "$plugin_root/../.." >/dev/null 2>&1 && pwd)"

plugin_version="$("${PYTHON:-python3}" - "$plugin_root/.codex-plugin/plugin.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
)"

npm_version="$("${PYTHON:-python3}" - "$repo_root/package.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
)"

if [ "$plugin_version" != "$npm_version" ]; then
  echo "Version mismatch: plugin=$plugin_version npm=$npm_version" >&2
  exit 1
fi

dist_dir="$repo_root/dist"
mkdir -p "$dist_dir"

npm pack --pack-destination "$dist_dir"
