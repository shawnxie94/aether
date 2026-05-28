import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class InstallLocalTests(unittest.TestCase):
    def test_install_preserves_existing_user_config_and_fills_defaults(self):
        repo_root = Path(__file__).resolve().parents[3]
        install_script = repo_root / "plugins" / "aether" / "scripts" / "install-local.sh"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aether_home = root / "aether-home"
            config_target = aether_home / "codex-plugin" / "config.json"
            config_target.parent.mkdir(parents=True)
            custom_db = root / "custom" / "aether.sqlite"
            config_target.write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": str(custom_db),
                        },
                        "embedding": {
                            "provider": "openai",
                            "providers": {
                                "openai": {
                                    "apiKeyEnv": "CUSTOM_OPENAI_KEY",
                                }
                            },
                        },
                        "generation": {
                            "defaultParams": {
                                "quality": "high",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = {
                **os.environ,
                "HOME": str(root / "home"),
                "CODEX_HOME": str(root / "codex-home"),
                "AETHER_HOME": str(aether_home),
                "AETHER_BIN_DIR": str(root / "bin"),
                "AETHER_CONFIG_DIR": str(root / "config" / "aether"),
            }

            subprocess.run([str(install_script)], cwd=repo_root, env=env, check=True, capture_output=True, text=True)

            installed_config = json.loads(config_target.read_text(encoding="utf-8"))

            self.assertEqual(installed_config["storage"]["databasePath"], str(custom_db))
            self.assertIn("assetRoot", installed_config["storage"])
            self.assertEqual(installed_config["embedding"]["provider"], "openai")
            self.assertEqual(installed_config["embedding"]["providers"]["openai"]["apiKeyEnv"], "CUSTOM_OPENAI_KEY")
            self.assertIn("model", installed_config["embedding"]["providers"]["openai"])
            self.assertEqual(installed_config["generation"]["defaultParams"]["quality"], "high")
            self.assertIn("aspectRatio", installed_config["generation"]["defaultParams"])
            self.assertTrue(config_target.with_suffix(".json.bak").exists())
            self.assertTrue((root / "config" / "aether" / "config.json").is_symlink())


if __name__ == "__main__":
    unittest.main()
