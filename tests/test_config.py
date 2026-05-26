import json
import tempfile
import unittest
from pathlib import Path

from aether_core.config import CONFIG_ENV, find_config, load_config


class ConfigTests(unittest.TestCase):
    def test_env_config_path_wins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "custom.json"
            config_path.write_text(
                json.dumps({"storage": {"databasePath": "db.sqlite"}}),
                encoding="utf-8",
            )

            found = find_config(Path(temp_dir), env={CONFIG_ENV: str(config_path)})

            self.assertEqual(found, config_path.resolve())

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

