import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aether_core.config import find_config, load_config


class ConfigTests(unittest.TestCase):
    def test_global_config_path_wins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            global_config = home / ".config" / "aether" / "config.json"
            global_config.parent.mkdir(parents=True)
            global_config.write_text(
                json.dumps({"storage": {"databasePath": "db.sqlite"}}),
                encoding="utf-8",
            )
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            (workspace / "config.json").write_text(
                json.dumps({"storage": {"databasePath": "workspace.sqlite"}}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"HOME": str(home)}):
                found = find_config(workspace)

            self.assertEqual(found, global_config.resolve())

    def test_workspace_config_path_wins_over_dot_aether(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            workspace_config = workspace / "config.json"
            workspace_config.write_text(
                json.dumps({"storage": {"databasePath": "workspace.sqlite"}}),
                encoding="utf-8",
            )
            dot_aether_config = workspace / ".aether" / "config.json"
            dot_aether_config.parent.mkdir()
            dot_aether_config.write_text(
                json.dumps({"storage": {"databasePath": "dot-aether.sqlite"}}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"HOME": str(home)}):
                found = find_config(workspace)

            self.assertEqual(found, workspace_config.resolve())

    def test_dot_aether_config_path_is_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            dot_aether_config = workspace / ".aether" / "config.json"
            dot_aether_config.parent.mkdir()
            dot_aether_config.write_text(
                json.dumps({"storage": {"databasePath": "dot-aether.sqlite"}}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"HOME": str(home)}):
                found = find_config(workspace)

            self.assertEqual(found, dot_aether_config.resolve())

    def test_relative_paths_resolve_from_config_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"storage": {"databasePath": ".aether/aether.sqlite"}}),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual(config.database_path, (Path(temp_dir) / ".aether/aether.sqlite").resolve())


if __name__ == "__main__":
    unittest.main()
