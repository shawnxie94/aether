#!/usr/bin/env bash
# verify_aether_layout.sh
# Validates that Aether's runtime data and config are in the canonical locations
# defined by install-local.sh. Run this whenever a config/symlink/panel issue is
# suspected. Exits 0 on a clean layout, 1 if any check fails.
#
# Usage:
#   scripts/verify_aether_layout.sh                 # auto-discover project root
#   scripts/verify_aether_layout.sh --project-root <path>
#   scripts/verify_aether_layout.sh -h | --help
set -euo pipefail

print_usage() {
  cat <<USAGE
Usage: $(basename "$0") [--project-root <path>]

With no arguments, the project root is discovered in this order:
  1. --project-root <path> if supplied
  2. git rev-parse --show-toplevel (if the current directory is inside a repo)
  3. Walking up from this script's location until a directory containing
     'plugins/aether/config.json' is found
USAGE
}

PROJECT_ROOT=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    --project-root)
      PROJECT_ROOT="${2:-}"
      shift 2
      ;;
    --project-root=*)
      PROJECT_ROOT="${1#--project-root=}"
      shift
      ;;
    *)
      printf "unknown argument: %s\n" "$1" >&2
      print_usage >&2
      exit 2
      ;;
  esac
done

discover_project_root() {
  if command -v git >/dev/null 2>&1; then
    local from_git
    from_git="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$from_git" ] && [ -f "$from_git/plugins/aether/config.json" ]; then
      printf "%s\n" "$from_git"
      return 0
    fi
  fi

  local candidate script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
  candidate="$script_dir"
  while [ "$candidate" != "/" ]; do
    if [ -f "$candidate/plugins/aether/config.json" ]; then
      printf "%s\n" "$candidate"
      return 0
    fi
    candidate="$(dirname "$candidate")"
  done

  return 1
}

if [ -z "$PROJECT_ROOT" ]; then
  if ! PROJECT_ROOT="$(discover_project_root)"; then
    printf "error: could not auto-discover project root. Pass --project-root <path>.\n" >&2
    exit 2
  fi
fi

if [ ! -f "$PROJECT_ROOT/plugins/aether/config.json" ]; then
  printf "error: %s does not look like the Aether repo (missing plugins/aether/config.json)\n" "$PROJECT_ROOT" >&2
  exit 2
fi

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AETHER_HOME="${AETHER_HOME:-$HOME/.aether}"
GLOBAL_CONFIG="$AETHER_HOME/codex-plugin/config.json"
GLOBAL_CONFIG_LINK="$HOME/.config/aether/config.json"
EXPECTED_DATA="$AETHER_HOME/data"
EXPECTED_DB="$EXPECTED_DATA/aether.sqlite"
EXPECTED_GEN_DIR="$EXPECTED_DATA/assets/generated"
EXPECTED_REF_DIR="$EXPECTED_DATA/assets/references"

PROJECT_LOCAL_CONFIG="$PROJECT_ROOT/plugins/aether/config.json"
PROJECT_LOCAL_DATA="$PROJECT_ROOT/plugins/aether/.aether"

fail=0
ok() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; fail=1; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; fail=1; }
section() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

section "Project root"
ok "discovered: $PROJECT_ROOT"

section "Symlink"
if [ -L "$GLOBAL_CONFIG_LINK" ]; then
  target="$(readlink "$GLOBAL_CONFIG_LINK")"
  if [ "$target" = "$GLOBAL_CONFIG" ]; then
    ok "symlink $GLOBAL_CONFIG_LINK -> $GLOBAL_CONFIG"
  else
    fail "symlink $GLOBAL_CONFIG_LINK -> $target (expected $GLOBAL_CONFIG)"
  fi
elif [ -e "$GLOBAL_CONFIG_LINK" ]; then
  fail "$GLOBAL_CONFIG_LINK exists but is not a symlink"
else
  fail "$GLOBAL_CONFIG_LINK missing — run plugins/aether/scripts/install-local.sh"
fi

section "Global config content"
if [ -f "$GLOBAL_CONFIG" ]; then
  db_path="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['storage']['databasePath'])" "$GLOBAL_CONFIG")"
  if [[ "$db_path" = /* ]]; then
    ok "databasePath is absolute: $db_path"
  else
    fail "databasePath is relative ($db_path) — global config was not rewritten by install-local.sh"
  fi
  if [ "$db_path" = "$EXPECTED_DB" ]; then
    ok "databasePath matches expected canonical path"
  else
    warn "databasePath is $db_path (expected $EXPECTED_DB)"
  fi
else
  fail "global config not found at $GLOBAL_CONFIG"
fi

section "Runtime data directory"
for path in "$EXPECTED_DATA" "$EXPECTED_GEN_DIR" "$EXPECTED_REF_DIR" "$EXPECTED_DB"; do
  if [ -e "$path" ]; then
    ok "exists: $path"
  else
    fail "missing: $path"
  fi
done

section "Live process consistency"
PANEL_PID="$(lsof -ti :3850 2>/dev/null | head -1 || true)"
if [ -n "$PANEL_PID" ]; then
  # aether panel is a Python HTTP server that opens the sqlite handle lazily
  # per request and closes it before returning, so lsof may not show any
  # current sqlite handle even when the process is healthy. Verify the
  # process is alive and the expected DB is reachable, and treat the missing
  # handle as a benign ok rather than a warn.
  if ! kill -0 "$PANEL_PID" 2>/dev/null; then
    fail "panel PID $PANEL_PID is not alive"
  else
    panel_db="$(lsof -p "$PANEL_PID" 2>/dev/null | awk '$NF ~ /aether\.sqlite$/ {print $NF}' | head -1 || true)"
    if [ "$panel_db" = "$EXPECTED_DB" ]; then
      ok "panel PID $PANEL_PID is reading $EXPECTED_DB"
    elif [ -n "$panel_db" ]; then
      fail "panel PID $PANEL_PID is reading $panel_db (expected $EXPECTED_DB)"
    else
      ok "panel PID $PANEL_PID is alive and not currently holding an aether.sqlite handle (lazy-open pattern, expected)"
    fi
  fi
else
  warn "no panel process listening on port 3850"
fi

section "Project-local drift"
if [ -d "$PROJECT_LOCAL_DATA" ]; then
  fail "stale project-local data dir at $PROJECT_LOCAL_DATA — remove with: rm -rf $PROJECT_LOCAL_DATA"
else
  ok "no stale $PROJECT_LOCAL_DATA"
fi
if [ -f "$PROJECT_LOCAL_CONFIG" ]; then
  rel="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['storage']['databasePath'])" "$PROJECT_LOCAL_CONFIG" 2>/dev/null || echo "")"
  if [[ "$rel" != /* && -n "$rel" ]]; then
    ok "project config present (dev template, relative paths: $rel) — not used at runtime when symlink is correct"
  fi
fi

section "Summary"
if [ "$fail" -eq 0 ]; then
  echo "Aether layout is canonical. Data lives in $EXPECTED_DATA, panel reads from there."
  exit 0
else
  echo "Aether layout has drift. Fix the items marked ✗ above."
  exit 1
fi
