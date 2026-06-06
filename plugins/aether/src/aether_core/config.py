from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GLOBAL_CONFIG_PATH = Path("~/.config/aether/config.json")


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    root: Path
    data: dict[str, Any]

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    @property
    def database_path(self) -> Path:
        return self.resolve_path(self.data["storage"]["databasePath"])


def find_config(start: Path | None = None) -> Path:
    env_candidate = os.environ.get("AETHER_CONFIG_PATH")
    if env_candidate:
        return Path(env_candidate).expanduser().resolve()

    global_candidate = GLOBAL_CONFIG_PATH.expanduser()
    if global_candidate.exists() or global_candidate.is_symlink():
        resolved = global_candidate.resolve()
        _validate_canonical_symlink_target(global_candidate, resolved)
        return resolved

    current = (start or Path.cwd()).resolve()
    for candidate_root in [current, *current.parents]:
        candidate = candidate_root / "config.json"
        if candidate.exists():
            return candidate

    workspace_candidate = current / ".aether" / "config.json"
    if workspace_candidate.exists():
        return workspace_candidate.resolve()

    raise FileNotFoundError("Could not find config.json for Aether.")


def _validate_canonical_symlink_target(link: Path, target: Path) -> None:
    """Refuse to silently use a project dev template when a global symlink is present.

    The global discovery entry point is ``~/.config/aether/config.json``. When this
    file is a symlink but the resolved target is a dev template with relative
    storage paths, treat the layout as broken and require an explicit opt-out via
    ``AETHER_ALLOW_PROJECT_CONFIG=1``. This catches the common case where the
    symlink has been (re)pointed at a repo-local ``config.json`` by mistake.
    """
    if os.environ.get("AETHER_ALLOW_PROJECT_CONFIG") == "1":
        return
    if not target.is_absolute():
        return
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return
    storage = data.get("storage") or {}
    db_path = storage.get("databasePath") or storage.get("database_path")
    if not db_path or Path(db_path).is_absolute():
        return
    raise RuntimeError(
        "Aether global config symlink "
        f"({link}) resolves to a dev template ({target}) "
        "with relative storage paths. Re-run "
        "plugins/aether/scripts/install-local.sh to restore the canonical layout, "
        "or set AETHER_ALLOW_PROJECT_CONFIG=1 to silence this check."
    )


def load_config(path: str | Path | None = None) -> LoadedConfig:
    config_path = Path(path).expanduser().resolve() if path else find_config()
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return LoadedConfig(path=config_path, root=config_path.parent, data=data)


def ensure_configured_dirs(config: LoadedConfig) -> list[Path]:
    storage = config.data.get("storage", {})
    keys = ["assetRoot", "referenceImageDir", "generatedImageDir", "runDir", "cacheDir"]
    paths = [config.resolve_path(storage[key]) for key in keys if key in storage]
    paths.append(config.database_path.parent)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths
