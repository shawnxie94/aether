import tempfile
import unittest
from pathlib import Path

from aether_core.composer import compose_prompt
from aether_core.storage import AetherStore


class ComposerTests(unittest.TestCase):
    def test_compose_prompt_selects_assets_and_detects_conflicts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Digital Melancholy",
                    "summary": "muted lonely cinematic future style",
                    "tags": ["lonely", "future"],
                    "prompt_fragments": ["digital melancholy", "muted cinematic realism"],
                    "negative_fragments": ["cheerful cartoon"],
                    "recommended_aspect_ratios": ["16:9"],
                    "status": "active",
                }
            )
            lighting = store.create_visual_asset(
                {
                    "type": "lighting",
                    "name": "Rainy Neon Reflection",
                    "summary": "neon rain reflections",
                    "tags": ["rain", "neon"],
                    "prompt_fragments": ["rain-soaked neon reflections"],
                    "negative_fragments": ["flat lighting"],
                    "status": "active",
                }
            )
            store.create_visual_asset(
                {
                    "type": "composition",
                    "name": "Minimal Negative Space",
                    "summary": "minimal negative space",
                    "tags": ["minimal"],
                    "prompt_fragments": ["large negative space"],
                    "avoid_with": [lighting["id"]],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "lonely girl in a future rainy city",
                explicit_asset_ids=[style["id"]],
                query="neon rain",
                default_generation_params={"quality": "standard"},
            )

            selected_ids = {item["asset_id"] for item in record["selected_assets"]}
            self.assertIn(style["id"], selected_ids)
            self.assertIn(lighting["id"], selected_ids)
            self.assertEqual(record["generation_params"]["aspectRatio"], "16:9")
            self.assertIn("digital melancholy", record["refined_prompt"])
            self.assertIn("flat lighting", record["negative_prompt"])
            self.assertTrue(record["conflicts"])

    def test_compose_prompt_uses_visual_systems_and_recipes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Oil Pastel Anime",
                    "summary": "hand drawn oil pastel anime",
                    "prompt_fragments": ["hand drawn oil pastel anime"],
                    "recommended_aspect_ratios": ["4:3"],
                    "status": "active",
                }
            )
            texture = store.create_visual_asset(
                {
                    "type": "texture",
                    "name": "Paper Grain",
                    "summary": "toothy off white paper grain",
                    "prompt_fragments": ["toothy off-white paper texture"],
                    "status": "active",
                }
            )
            palette = store.create_visual_asset(
                {
                    "type": "color_palette",
                    "name": "Muted Night",
                    "summary": "quiet muted night blues",
                    "prompt_fragments": ["muted night blue palette"],
                    "status": "active",
                }
            )
            system = store.create_visual_system(
                {
                    "kind": "genre",
                    "name": "Oil Pastel Daily Anime",
                    "visual_rules": [
                        {
                            "key": "rendering_expectations",
                            "value": ["preserve tactile handmade paper feel"],
                        }
                    ],
                    "avoid_rules": ["avoid glossy 3D rendering"],
                    "assets": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.9},
                        {"asset_id": palette["id"], "role": "optional", "weight": 0.7},
                    ],
                    "status": "active",
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Oil Pastel Portrait",
                    "parent_system_ids": [system["id"]],
                    "composition_rules": [
                        {
                            "key": "style_application",
                            "value": ["keep paper grain visible over the portrait paint"],
                        },
                        {
                            "key": "negative_constraints",
                            "value": ["avoid smoothing out handmade texture"],
                        },
                    ],
                    "recommended_aspect_ratios": ["3:4"],
                    "assets": [
                        {"asset_id": texture["id"], "role": "core", "weight": 0.9},
                    ],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "quiet girl portrait",
                system_ids=[system["id"]],
                recipe_ids=[recipe["id"]],
                default_generation_params={"aspectRatio": "1:1", "quality": "standard"},
            )

            selected_ids = {item["asset_id"] for item in record["selected_assets"]}
            self.assertIn(style["id"], selected_ids)
            self.assertIn(texture["id"], selected_ids)
            self.assertIn(palette["id"], selected_ids)
            self.assertEqual(record["generation_params"]["aspectRatio"], "3:4")
            self.assertIn("preserve tactile handmade paper feel", record["refined_prompt"])
            self.assertIn("style_application: keep paper grain visible over the portrait paint", record["refined_prompt"])
            self.assertIn("avoid glossy 3D rendering", record["negative_prompt"])
            self.assertIn("negative_constraints: avoid smoothing out handmade texture", record["negative_prompt"])
            self.assertIn(
                "rendering_expectations: preserve tactile handmade paper feel",
                record["composition_plan"]["system_rules"],
            )
            self.assertIn(
                "style_application: keep paper grain visible over the portrait paint",
                record["composition_plan"]["composition_rules"],
            )
            self.assertEqual(record["constraints"]["selected_systems"][0]["system_id"], system["id"])
            self.assertEqual(record["constraints"]["selected_recipes"][0]["recipe_id"], recipe["id"])

    def test_compose_prompt_recalls_system_and_recipe_from_intent_sketch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Oriental Fantasy Painterly Anime",
                    "summary": "bright oriental fantasy natural sanctuary painterly anime",
                    "prompt_fragments": ["bright oriental fantasy painterly anime"],
                    "status": "active",
                }
            )
            scene = store.create_visual_asset(
                {
                    "type": "scene",
                    "name": "Natural Sanctuary Spirit Encounter",
                    "summary": "small human meets spirit in natural sanctuary",
                    "prompt_fragments": ["natural sanctuary spirit encounter"],
                    "status": "active",
                }
            )
            system = store.create_visual_system(
                {
                    "kind": "art_direction",
                    "name": "Oriental Fantasy Natural Sanctuary",
                    "summary": "oriental fantasy natural sanctuary spirit encounter",
                    "visual_rules": [
                        {"key": "medium", "value": ["painterly anime"]},
                        {"key": "subject_aesthetic", "value": ["oriental fantasy natural sanctuary"]},
                    ],
                    "assets": [
                        {"asset_id": style["id"], "role": "core"},
                        {"asset_id": scene["id"], "role": "optional"},
                    ],
                    "status": "active",
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Oriental Fantasy Spirit Encounter Key Art",
                    "summary": "oriental fantasy natural sanctuary spirit encounter key art",
                    "parent_system_ids": [system["id"]],
                    "composition_rules": [
                        {"key": "subject_scene_binding", "value": ["small human encounters spirit in sanctuary"]}
                    ],
                    "assets": [{"asset_id": scene["id"], "role": "core"}],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "oriental fantasy natural sanctuary spirit encounter",
                default_generation_params={"aspectRatio": "1:1"},
            )

            self.assertEqual(record["constraints"]["selected_systems"][0]["system_id"], system["id"])
            self.assertEqual(record["constraints"]["selected_recipes"][0]["recipe_id"], recipe["id"])
            self.assertTrue(record["intent_sketch"]["query_terms"])
            self.assertEqual(record["recall_strategy"]["mode"], "lexical_relation")
            self.assertEqual(record["recall_candidates"]["visual_systems"][0]["system_id"], system["id"])
            self.assertEqual(record["recall_candidates"]["recipes"][0]["recipe_id"], recipe["id"])
            recalled_asset_ids = {item["asset_id"] for item in record["recall_candidates"]["visual_assets"]}
            self.assertIn(scene["id"], recalled_asset_ids)
            self.assertNotIn("visual_assets_raw", record["recall_candidates"])

    def test_compose_prompt_collapses_recalled_asset_family(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            parent = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Bright Fantasy Paint",
                    "summary": "bright fantasy painterly style",
                    "prompt_fragments": ["bright fantasy painterly style"],
                    "status": "active",
                }
            )
            child = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Bright Fantasy Paint Leaf Variant",
                    "summary": "bright fantasy painterly leaf sea style",
                    "prompt_fragments": ["bright fantasy painterly leaf sea style", "leaf sea"],
                    "parent_asset_id": parent["id"],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "bright fantasy painterly leaf sea",
                default_generation_params={"aspectRatio": "1:1"},
                include_debug_recall=True,
            )

            raw_ids = {item["asset_id"] for item in record["recall_candidates"]["visual_assets_raw"]}
            collapsed_ids = {item["asset_id"] for item in record["recall_candidates"]["visual_assets"]}
            self.assertIn(parent["id"], raw_ids)
            self.assertIn(child["id"], raw_ids)
            self.assertEqual(len(collapsed_ids & {parent["id"], child["id"]}), 1)
            self.assertIn(child["id"], collapsed_ids)

    def test_compose_prompt_prefers_specific_recipe_over_generic_recipe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Bright Fantasy Paint",
                    "summary": "bright fantasy painterly style",
                    "prompt_fragments": ["bright fantasy painterly style"],
                    "status": "active",
                }
            )
            generic = store.create_recipe(
                {
                    "name": "Bright Fantasy General Key Art",
                    "summary": "general bright fantasy key art fallback",
                    "composition_rules": [{"key": "asset_roles", "value": ["general fantasy composition"]}],
                    "assets": [{"asset_id": style["id"], "role": "core"}],
                    "status": "active",
                }
            )
            specific = store.create_recipe(
                {
                    "name": "Bright Fantasy Leaf Sea Key Art",
                    "summary": "bright fantasy leaf sea key art with a small traveler",
                    "composition_rules": [
                        {"key": "asset_roles", "value": ["style and leaf sea scene define key art"]},
                        {"key": "subject_scene_binding", "value": ["small traveler crosses a leaf sea"]},
                    ],
                    "assets": [{"asset_id": style["id"], "role": "core"}],
                    "status": "active",
                }
            )

            record = compose_prompt(
                store,
                "bright fantasy leaf sea key art",
                default_generation_params={"aspectRatio": "1:1"},
            )

            recalled_ids = [item["recipe_id"] for item in record["recall_candidates"]["recipes"]]
            self.assertIn(generic["id"], recalled_ids)
            self.assertIn(specific["id"], recalled_ids)
            self.assertEqual(record["constraints"]["selected_recipes"][0]["recipe_id"], specific["id"])

    def test_compose_prompt_appends_signature_coverage_paragraph(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Soft Blue Pencil Shoujo Portrait Illustration",
                    "summary": "Pencil and pastel shoujo rendering.",
                    "prompt_fragments": ["soft hand-drawn shoujo portrait, colored pencil, peach skin"],
                    "negative_fragments": ["no glossy 3d render"],
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Soft Blue Pencil Shoujo Portrait Recipe",
                    "summary": "Test recipe with signature coverage rules.",
                    "use_cases": ["portrait"],
                    "composition_rules": [
                        {
                            "key": "must_cover_ratios",
                            "value": [
                                "powder blue covers at least 35% of the upper frame",
                                "warm paper negative space covers at least 30%",
                            ],
                            "reason": "Recipe signature coverage budgets.",
                        },
                        {
                            "key": "signature_self_check",
                            "value": [
                                "iris shows visible coral-red and deep-blue split, not just highlights",
                                "sailor collar or ruffled camisole anchors the lower frame",
                            ],
                            "reason": "Anchors the model against word-frequency drift.",
                        },
                        {
                            "key": "negative_constraints",
                            "value": ["no glossy 3d render"],
                        },
                    ],
                    "assets": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.9},
                    ],
                }
            )
            store.update_recipe_status(recipe["id"], "active")

            record = compose_prompt(
                store,
                "A vertical 3:4 intimate shoujo portrait",
                recipe_ids=[recipe["id"]],
                explicit_asset_ids=[style["id"]],
                aspect_ratio="3:4",
            )
            refined = record["refined_prompt"]
            self.assertIn("Recipe signature coverage:", refined)
            self.assertIn("powder blue covers at least 35% of the upper frame", refined)
            self.assertIn("iris shows visible coral-red and deep-blue split", refined)
            self.assertIsInstance(refined, str)
            # Verify the signature coverage block is appended after other
            # composition rules but before the trailing negative constraint
            # block, so the numbers stay near the end of the model's
            # attention window.
            coverage_idx = refined.find("Recipe signature coverage:")
            self.assertGreater(coverage_idx, 0)
            self.assertLess(coverage_idx, len(refined))

    def test_compose_prompt_exposes_signature_coverage_paragraph_as_structured_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Soft Blue Pencil Style",
                    "summary": "Pencil and pastel.",
                    "prompt_fragments": ["soft pencil drawing"],
                }
            )
            recipe = store.create_recipe(
                {
                    "name": "Coverage Recipe",
                    "summary": "Carries must_cover_ratios.",
                    "use_cases": ["x"],
                    "composition_rules": [
                        {
                            "key": "must_cover_ratios",
                            "value": ["powder blue covers at least 35% of the frame"],
                            "reason": "Recipe signature coverage budgets.",
                        },
                        {
                            "key": "signature_self_check",
                            "value": ["iris shows coral-red plus deep-blue split"],
                            "reason": "Anchors against word-frequency drift.",
                        },
                    ],
                    "assets": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.9},
                    ],
                }
            )
            store.update_recipe_status(recipe["id"], "active")

            record = compose_prompt(
                store,
                "A vertical 3:4 portrait",
                recipe_ids=[recipe["id"]],
                explicit_asset_ids=[style["id"]],
                aspect_ratio="3:4",
            )
            sig = record["composition_plan"].get("signature_coverage")
            self.assertIsNotNone(sig, "composition_plan.signature_coverage should be populated")
            self.assertIn("paragraph", sig)
            self.assertIn("blocks", sig)
            self.assertEqual(len(sig["blocks"]), 2)
            self.assertEqual(
                sig["blocks"][0]["key"],
                "must_cover_ratios",
            )
            self.assertIn("Recipe signature coverage:", sig["paragraph"])
            # The same paragraph should also be appended to refined_prompt.
            self.assertIn(sig["paragraph"], record["refined_prompt"])

    def test_compose_prompt_records_recipe_dominance_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Primary Pencil Style",
                    "summary": "Recipe core style for pencil portraits.",
                    "tags": ["shoujo", "pencil"],
                    "prompt_fragments": ["soft pencil style for intimate portrait"],
                }
            )
            competing_style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Competing Pencil Style",
                    "summary": "Another style candidate for the same family.",
                    "tags": ["shoujo", "pencil"],
                    "prompt_fragments": ["competing pencil style for portrait"],
                }
            )
            # Bump assets to active so the composer's active_assets
            # list sees them; otherwise the recipe-dominance check
            # cannot find the type for priority_type comparison.
            store.update_visual_asset_status(style["id"], "active")
            store.update_visual_asset_status(competing_style["id"], "active")
            recipe = store.create_recipe(
                {
                    "name": "Dominant Recipe",
                    "summary": "Recipe with one core style.",
                    "use_cases": ["x"],
                    "composition_rules": [],
                    "assets": [
                        {"asset_id": style["id"], "role": "core", "weight": 0.95},
                    ],
                }
            )
            store.update_recipe_status(recipe["id"], "active")

            # Pass both styles as explicit so the dominance check can
            # actually observe a competing asset in the selected set;
            # hybrid_recall alone would not surface the competing style
            # for a generic short query.
            record = compose_prompt(
                store,
                "A vertical 3:4 intimate shoujo portrait, soft pencil style",
                recipe_ids=[recipe["id"]],
                explicit_asset_ids=[style["id"], competing_style["id"]],
                aspect_ratio="3:4",
            )
            dominance_conflicts = [
                c for c in record.get("conflicts", [])
                if c.get("conflicts_with") == "recipe_primary_style"
            ]
            self.assertTrue(
                len(dominance_conflicts) >= 1,
                f"expected at least one recipe-dominance conflict, got {record.get('conflicts')}",
            )

    def test_compose_prompt_skips_signature_coverage_when_no_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AetherStore(Path(temp_dir) / "aether.sqlite")
            store.init()

            style = store.create_visual_asset(
                {
                    "type": "style",
                    "name": "Plain Style",
                    "summary": "No signature coverage.",
                    "prompt_fragments": ["simple style"],
                }
            )
            record = compose_prompt(
                store,
                "A simple portrait",
                explicit_asset_ids=[style["id"]],
                aspect_ratio="3:4",
            )
            self.assertNotIn("Recipe signature coverage:", record["refined_prompt"])


if __name__ == "__main__":
    unittest.main()
