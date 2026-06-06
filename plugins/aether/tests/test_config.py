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
            # Use an absolute databasePath so the canonical-symlink safety
            # check does not reject the file. The test's intent is to verify
            # discovery order (global wins over workspace), not to exercise
            # the safety check.
            global_config.write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": str(
                                Path(temp_dir) / "global.sqlite"
                            )
                        }
                    }
                ),
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

class CanonicalSymlinkSafetyCheckTests(unittest.TestCase):
    """Verify that find_config refuses a dev template that is reachable through
    the global symlink, unless the explicit opt-out env var is set."""

    def test_relative_path_in_global_symlink_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            global_config = home / ".config" / "aether" / "config.json"
            global_config.parent.mkdir(parents=True)
            global_config.write_text(
                json.dumps(
                    {"storage": {"databasePath": "dev/aether.sqlite"}}
                ),
                encoding="utf-8",
            )
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            with patch.dict(os.environ, {"HOME": str(home)}, clear=False):
                # Make sure the opt-out is not set
                os.environ.pop("AETHER_ALLOW_PROJECT_CONFIG", None)
                with self.assertRaises(RuntimeError) as ctx:
                    find_config(workspace)
            self.assertIn("dev template", str(ctx.exception))

    def test_opt_out_env_var_allows_relative_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            global_config = home / ".config" / "aether" / "config.json"
            global_config.parent.mkdir(parents=True)
            global_config.write_text(
                json.dumps(
                    {"storage": {"databasePath": "dev/aether.sqlite"}}
                ),
                encoding="utf-8",
            )
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            with patch.dict(
                os.environ,
                {
                    "HOME": str(home),
                    "AETHER_ALLOW_PROJECT_CONFIG": "1",
                },
            ):
                found = find_config(workspace)
            self.assertEqual(found, global_config.resolve())

    def test_absolute_path_in_global_symlink_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            global_config = home / ".config" / "aether" / "config.json"
            global_config.parent.mkdir(parents=True)
            global_config.write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": str(
                                Path(temp_dir) / "canonical.sqlite"
                            )
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            with patch.dict(os.environ, {"HOME": str(home)}):
                found = find_config(workspace)
            self.assertEqual(found, global_config.resolve())
