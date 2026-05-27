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
    if global_candidate.exists():
        return global_candidate.resolve()

    current = (start or Path.cwd()).resolve()
    for candidate_root in [current, *current.parents]:
        candidate = candidate_root / "config.json"
        if candidate.exists():
            return candidate

    workspace_candidate = current / ".aether" / "config.json"
    if workspace_candidate.exists():
        return workspace_candidate.resolve()

    raise FileNotFoundError("Could not find config.json for Aether.")


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
