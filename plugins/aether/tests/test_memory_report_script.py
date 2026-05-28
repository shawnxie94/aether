import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "visual-memory" / "scripts" / "memory_report.py"


class MemoryReportScriptTests(unittest.TestCase):
    def test_memory_report_outputs_summary_and_optional_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "storage": {
                            "databasePath": "aether.sqlite",
                            "assetRoot": "assets",
                            "referenceImageDir": "assets/references",
                            "generatedImageDir": "assets/generated",
                            "cacheDir": "cache",
                            "runDir": "runs",
                        }
                    }
                ),
                encoding="utf-8",
            )

            summary = subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                check=True,
                capture_output=True,
                text=True,
            )
            summary_output = json.loads(summary.stdout)
            self.assertEqual(summary_output["summary"]["visual_asset_count"], 0)

            full = subprocess.run(
                [sys.executable, str(SCRIPT), "--all"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                check=True,
                capture_output=True,
                text=True,
            )
            full_output = json.loads(full.stdout)
            self.assertIn("active_visual_assets", full_output)
            self.assertIn("pending", full_output)
            self.assertIn("quality", full_output)
            self.assertIn("recent_generations", full_output)


if __name__ == "__main__":
    unittest.main()
