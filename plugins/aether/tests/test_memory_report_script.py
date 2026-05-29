import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aether_core.storage import AetherStore


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

            store = AetherStore(root / "aether.sqlite")
            store.init()
            store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Compact Style",
                    "summary": "compact report style",
                    "prompt_fragments": ["x" * 1000],
                    "negative_fragments": ["avoid"],
                    "status": "active",
                }
            )

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
            self.assertIn("prompt_fragment_count", full_output["active_visual_assets"][0])
            self.assertNotIn("prompt_fragments", full_output["active_visual_assets"][0])

            full_records = subprocess.run(
                [sys.executable, str(SCRIPT), "--assets", "--full"],
                cwd=root,
                env={**os.environ, "HOME": str(root)},
                check=True,
                capture_output=True,
                text=True,
            )
            full_records_output = json.loads(full_records.stdout)
            self.assertIn("prompt_fragments", full_records_output["active_visual_assets"][0])


if __name__ == "__main__":
    unittest.main()
