import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aether_core.assets import ingest_asset
from aether_core.config import load_config
from aether_core.storage import (
    AetherStore,
    _EMPTY_FOOTPRINT_TYPE,
    _FOOTPRINT_TYPE_MAP,
)


class FootprintTypeMapTests(unittest.TestCase):
    """Verify that _merge_image_fingerprint_into_profile respects the
    per-type footprint mapping. These tests catch the "no-brain full
    merge" regression where color_palette assets ended up with
    ``stats.exposure`` and lighting assets ended up with
    ``dominant_hex``.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self._write_config()
        # Build one warm + one cool reference image so the resulting
        # fingerprint has real palette and stats to project.
        self.warm_path = self.root / "warm.png"
        self.cool_path = self.root / "cool.png"
        self._write_warm(self.warm_path)
        self._write_cool(self.cool_path)
        self.store = AetherStore(self.config.database_path)
        self.store.init()
        self.warm_record = ingest_asset(self.config, self.warm_path, "reference")
        self.cool_record = ingest_asset(self.config, self.cool_path, "reference")
        self.warm_asset = self.store.create_asset(self.warm_record)
        self.cool_asset = self.store.create_asset(self.cool_record)
        self.warm_fingerprint = self.warm_record["fingerprint"]

    def _write_config(self):
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "storage": {
                        "databasePath": "aether.sqlite",
                        "assetRoot": "assets",
                        "referenceImageDir": "assets/references",
                        "generatedImageDir": "assets/generated",
                        "cacheDir": "cache",
                    }
                }
            ),
            encoding="utf-8",
        )
        return load_config(config_path)

    def _write_warm(self, path: Path) -> None:
        image = Image.new("RGB", (96, 96), (240, 235, 220))
        for x in range(16, 40):
            for y in range(16, 40):
                image.putpixel((x, y), (220, 80, 70))
        image.save(path)

    def _write_cool(self, path: Path) -> None:
        image = Image.new("RGB", (96, 96), (40, 60, 100))
        for x in range(16, 40):
            for y in range(16, 40):
                image.putpixel((x, y), (20, 180, 160))
        image.save(path)

    def _make_visual_asset(self, asset_type: str) -> dict:
        return {
            "type": asset_type,
            "name": f"{asset_type} sample",
            "summary": "test",
            "source_references": [
                {
                    "image_path": self.warm_record["asset_path"],
                    "asset_id": self.warm_asset["id"],
                }
            ],
        }

    def test_color_palette_absorbs_palette_not_stats(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("color_palette")
        )
        # Palette fields flow in.
        self.assertIn("dominant_hex", merged)
        self.assertIn("temperature", merged)
        # Stats fields must not leak in.
        self.assertNotIn("exposure", merged)
        self.assertNotIn("edge_density", merged)
        self.assertNotIn("low_frequency_ratio", merged)
        # image_fingerprint snapshot only carries the palette block.
        snapshot = merged["image_fingerprint"]
        self.assertIn("palette", snapshot)
        self.assertNotIn("geometry", snapshot)
        self.assertNotIn("stats", snapshot)

    def test_lighting_absorbs_stats_not_palette(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("lighting")
        )
        # Stats fields flow in.
        self.assertIn("exposure", merged)
        self.assertIn("dynamic_range", merged)
        # Palette fields must not leak in.
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("accent_hex", merged)
        self.assertNotIn("temperature", merged)
        # image_fingerprint snapshot only carries stats.
        snapshot = merged["image_fingerprint"]
        self.assertIn("stats", snapshot)
        self.assertNotIn("palette", snapshot)
        self.assertNotIn("geometry", snapshot)

    def test_composition_absorbs_geometry_only(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("composition")
        )
        # Only the snapshot carries geometry; profile field name
        # ``subject_bbox`` is not in compositionProfile so we do not
        # set it as a top-level key.
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("exposure", merged)
        self.assertNotIn("edge_density", merged)
        snapshot = merged["image_fingerprint"]
        self.assertIn("geometry", snapshot)
        self.assertNotIn("palette", snapshot)
        self.assertNotIn("stats", snapshot)

    def test_shape_line_absorbs_edge_density(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("shape_line")
        )
        self.assertIn("edge_density", merged)
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("low_frequency_ratio", merged)
        snapshot = merged["image_fingerprint"]
        self.assertIn("stats", snapshot)
        self.assertNotIn("palette", snapshot)
        self.assertNotIn("geometry", snapshot)

    def test_texture_absorbs_frequency_ratios_not_edge(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("texture")
        )
        self.assertIn("low_frequency_ratio", merged)
        self.assertIn("mid_frequency_ratio", merged)
        self.assertIn("high_frequency_ratio", merged)
        # Edge density belongs to shape_line, not texture.
        self.assertNotIn("edge_density", merged)
        # And the palette must not leak into texture.
        self.assertNotIn("dominant_hex", merged)

    def test_mood_absorbs_temperature_and_exposure(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("mood")
        )
        self.assertIn("temperature", merged)
        self.assertIn("exposure", merged)
        # Mood does not consume raw hex values or geometry.
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("subject_bbox", merged)
        # And it does not consume texture statistics.
        self.assertNotIn("edge_density", merged)
        self.assertNotIn("low_frequency_ratio", merged)
        snapshot = merged["image_fingerprint"]
        self.assertIn("palette", snapshot)
        self.assertIn("stats", snapshot)
        self.assertNotIn("geometry", snapshot)

    def test_scene_absorbs_palette_and_geometry(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("scene")
        )
        # Scene takes only the temperature / saturation cues into its
        # profile (not the raw hex) so the asset stays descriptive
        # rather than prescriptive about specific colors.
        self.assertIn("temperature", merged)
        self.assertIn("saturation", merged)
        self.assertNotIn("dominant_hex", merged)
        snapshot = merged["image_fingerprint"]
        # The snapshot still carries the full palette and geometry for
        # callers that want to inspect the underlying fingerprint.
        self.assertIn("palette", snapshot)
        self.assertIn("geometry", snapshot)
        self.assertNotIn("stats", snapshot)

    def test_style_absorbs_everything(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("style")
        )
        # Style is the aggregate type.
        self.assertIn("dominant_hex", merged)
        self.assertIn("exposure", merged)
        self.assertIn("edge_density", merged)
        self.assertIn("low_frequency_ratio", merged)
        snapshot = merged["image_fingerprint"]
        self.assertIn("palette", snapshot)
        self.assertIn("geometry", snapshot)
        self.assertIn("stats", snapshot)

    def test_camera_absorbs_geometry_and_exposure_only(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("camera")
        )
        self.assertIn("exposure", merged)
        snapshot = merged["image_fingerprint"]
        self.assertIn("geometry", snapshot)
        self.assertIn("stats", snapshot)
        # Camera does not consume hex or texture data.
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("low_frequency_ratio", merged)
        self.assertNotIn("edge_density", merged)
        self.assertNotIn("palette", snapshot)

    def test_character_gets_nothing(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("character")
        )
        # Character relies on target detection; the fingerprint
        # pipeline must not pre-empt that work by leaking color cues.
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("exposure", merged)
        self.assertNotIn("image_fingerprint", merged)

    def test_prop_symbol_gets_nothing(self) -> None:
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("prop_symbol")
        )
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("exposure", merged)
        self.assertNotIn("image_fingerprint", merged)

    def test_negative_rule_gets_nothing(self) -> None:
        # The whole point of negative rules is to avoid certain
        # visual traits; surfacing the avoided fingerprint would
        # self-defeat the rule.
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("negative_rule")
        )
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("image_fingerprint", merged)
        self.assertEqual(merged, {})

    def test_unknown_type_falls_back_to_empty(self) -> None:
        # Future / unknown types must default to no-merge rather than
        # silently dumping every fingerprint block.
        merged = self.store._merge_image_fingerprint_into_profile(
            {}, self._make_visual_asset("made_up_type")
        )
        self.assertNotIn("dominant_hex", merged)
        self.assertNotIn("image_fingerprint", merged)

    def test_type_map_is_complete(self) -> None:
        # Sanity: every type in VISUAL_ASSET_PROFILE_KEYS_BY_TYPE
        # (the schema's authoritative type list) must have an entry,
        # otherwise we silently lose the merge for that type.
        from aether_core.validation import VISUAL_ASSET_PROFILE_KEYS_BY_TYPE
        missing = set(VISUAL_ASSET_PROFILE_KEYS_BY_TYPE.keys()) - set(
            _FOOTPRINT_TYPE_MAP.keys()
        )
        self.assertEqual(missing, set(), f"missing mapping for: {missing}")

    def test_empty_fallback_is_pure_noop(self) -> None:
        self.assertEqual(_EMPTY_FOOTPRINT_TYPE["palette"], False)
        self.assertEqual(_EMPTY_FOOTPRINT_TYPE["stats_fields"], [])
        self.assertEqual(_EMPTY_FOOTPRINT_TYPE["include_palette"], False)
        self.assertEqual(_EMPTY_FOOTPRINT_TYPE["include_geometry"], False)
        self.assertEqual(_EMPTY_FOOTPRINT_TYPE["include_stats"], False)


if __name__ == "__main__":
    unittest.main()


class FootprintCanonicalTextTests(unittest.TestCase):
    """Verify canonical text is also type-aware. A lighting asset's
    canonical embedding text must not mention "aspect ratio" or
    "edge density" (those are shape_line / composition territory)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self._write_config()
        self.warm_path = self.root / "warm.png"
        image = Image.new("RGB", (96, 96), (240, 235, 220))
        for x in range(16, 40):
            for y in range(16, 40):
                image.putpixel((x, y), (220, 80, 70))
        image.save(self.warm_path)
        self.store = AetherStore(self.config.database_path)
        self.store.init()
        self.warm_record = ingest_asset(self.config, self.warm_path, "reference")
        self.warm_asset = self.store.create_asset(self.warm_record)
        self.entity = {
            "type": "lighting",
            "name": "test",
            "source_references": [
                {"image_path": self.warm_record["asset_path"], "asset_id": self.warm_asset["id"]}
            ],
        }

    def _write_config(self):
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "storage": {
                        "databasePath": "aether.sqlite",
                        "assetRoot": "assets",
                        "referenceImageDir": "assets/references",
                        "generatedImageDir": "assets/generated",
                        "cacheDir": "cache",
                    }
                }
            ),
            encoding="utf-8",
        )
        return load_config(config_path)

    def test_lighting_canonical_text_skips_geometry_and_palette(self) -> None:
        text = self.store._visual_asset_fingerprint_text(self.entity)
        # Lighting is allowed stats only. No aspect, no edge density,
        # no hex strings.
        self.assertIn("exposure", text)
        self.assertNotIn("aspect", text)
        self.assertNotIn("edge", text)
        self.assertNotIn("hex", text)

    def test_color_palette_canonical_text_skips_geometry(self) -> None:
        entity = dict(self.entity)
        entity["type"] = "color_palette"
        text = self.store._visual_asset_fingerprint_text(entity)
        self.assertIn("palette hex", text)
        self.assertIn("temperature", text)
        self.assertNotIn("aspect", text)
        self.assertNotIn("exposure", text)
        self.assertNotIn("edge", text)

    def test_character_canonical_text_is_empty(self) -> None:
        entity = dict(self.entity)
        entity["type"] = "character"
        text = self.store._visual_asset_fingerprint_text(entity)
        self.assertEqual(text, "")

    def test_shape_line_canonical_text_mentions_edge_only(self) -> None:
        entity = dict(self.entity)
        entity["type"] = "shape_line"
        text = self.store._visual_asset_fingerprint_text(entity)
        self.assertIn("edge_density", text)
        self.assertNotIn("hex", text)
        self.assertNotIn("aspect", text)
        self.assertNotIn("frequency", text)


if __name__ == "__main__":
    unittest.main()
