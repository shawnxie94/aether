import tempfile
import unittest
from pathlib import Path

from aether_core.config import load_config
from aether_core.generation_service import record_generation_run
from aether_core.storage import AetherStore


class GenerationServiceTests(unittest.TestCase):
    def _config_and_store(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        config_path = root / "config.json"
        config_path.write_text(
            "{"
            '"storage": {'
            '"databasePath": "aether.sqlite",'
            '"assetRoot": "assets",'
            '"referenceImageDir": "assets/references",'
            '"generatedImageDir": "assets/generated",'
            '"runDir": "runs",'
            '"cacheDir": "cache"'
            "},"
            '"generation": {"defaultParams": {"aspectRatio": "1:1", "quality": "standard"}}'
            "}",
            encoding="utf-8",
        )
        config = load_config(config_path)
        store = AetherStore(config.database_path)
        store.init()
        return root, config, store

    def test_record_generation_run_orchestrates_relations_and_defaults(self):
        root, config, store = self._config_and_store()
        style = store.create_visual_asset(
            {
                "type": "style",
                "name": "Soft Gouache",
                "summary": "soft gouache rendering",
                "status": "active",
            }
        )
        recipe = store.create_recipe(
            {
                "name": "Portrait Recipe",
                "summary": "portrait composition",
                "assets": [{"asset_id": style["id"], "role": "core"}],
                "status": "active",
            }
        )
        output = root / "provider-output.png"
        output.write_bytes(b"fake png")

        record = record_generation_run(
            config,
            store,
            {
                "source_prompt": "a quiet portrait",
                "refined_prompt": "a quiet portrait, soft gouache rendering",
                "generation_skill": "imagegen",
                "recipe_id": recipe["id"],
                "outputs": [str(output)],
                "status": "generated",
            },
            apply_review_default=True,
        )

        self.assertEqual(record["skill_params"]["aspectRatio"], "1:1")
        self.assertEqual(record["skill_params"]["quality"], "standard")
        self.assertEqual(record["selected_assets"], [style["id"]])
        self.assertEqual(record["visual_review"]["style_consistency"], "not_reviewed")
        self.assertEqual(record["outputs"][0]["original_output"], str(output))
        persisted = store.get_generation_run(record["id"])
        self.assertEqual(persisted["recipe_id"], recipe["id"])
        self.assertEqual(persisted["selected_assets"], [style["id"]])

    def test_failed_run_gets_review_placeholder_without_archiving_output(self):
        _, config, store = self._config_and_store()

        record = record_generation_run(
            config,
            store,
            {
                "refined_prompt": "a failed request",
                "generation_skill": "imagegen",
                "status": "failed",
                "error": "provider unavailable",
                "outputs": [],
            },
            apply_review_default=True,
        )

        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["outputs"], [])
        self.assertEqual(record["visual_review"]["style_consistency"], "not_reviewed")
        self.assertIn("provider unavailable", record["visual_review"]["deviations"][0])
        self.assertEqual(store.list_assets(kind="generated", limit=None), [])


if __name__ == "__main__":
    unittest.main()
