import contextlib
import io
import unittest

from aether_core.cli import build_parser, candidate_payload_summary, visual_asset_candidate_summary


class CliTests(unittest.TestCase):
    def test_help_text_explains_common_entrypoints(self):
        parser = build_parser()
        root_help = parser.format_help()
        self.assertIn("Codex visual memory", root_help)
        self.assertIn("visual-asset", root_help)
        self.assertIn("generation", root_help)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            with self.assertRaises(SystemExit):
                parser.parse_args(["visual-asset", "list", "--help"])
        self.assertIn("List saved visual memories", stdout.getvalue())

    def test_visual_asset_candidate_summary_uses_evolution_fields(self):
        summary = visual_asset_candidate_summary(
            {
                "id": "candidate_style",
                "batch_id": "batch",
                "type": "style",
                "name": "Painterly Style",
                "reuse_score": 0.74,
                "decision": "inherit_variant",
                "target_asset_id": "legacy_target",
                "similar_candidates": [{"asset_id": "target_asset", "name": "Target Painterly Style"}],
                "status": "pending",
                "confirmed_asset_id": None,
                "updated_at": "2026-05-28T00:00:00+00:00",
                "payload": {
                    "evolution_action": "inherit_variant",
                    "evolution_suggestion": {"action": "inherit_variant", "target_id": "target_asset"},
                },
            }
        )

        self.assertEqual(summary["dedupe_score"], 0.74)
        self.assertEqual(summary["evolution_action"], "inherit_variant")
        self.assertEqual(summary["target_id"], "target_asset")
        self.assertEqual(summary["target_name"], "Target Painterly Style")
        self.assertNotIn("decision", summary)
        self.assertNotIn("reuse_score", summary)
        self.assertNotIn("target_asset_id", summary)

        create_summary = visual_asset_candidate_summary(
            {
                "id": "candidate_new",
                "batch_id": "batch",
                "type": "style",
                "name": "New Style",
                "reuse_score": 0.1,
                "decision": "create_new",
                "target_asset_id": "stale_target",
                "similar_candidates": [],
                "status": "pending",
                "confirmed_asset_id": None,
                "updated_at": "2026-05-28T00:00:00+00:00",
                "payload": {
                    "evolution_action": "create_new",
                    "evolution_suggestion": {"action": "create_new"},
                },
            }
        )
        self.assertIsNone(create_summary["target_id"])
        self.assertIsNone(create_summary["target_name"])

    def test_payload_candidate_summary_includes_target_name(self):
        summary = candidate_payload_summary(
            {
                "id": "system_candidate",
                "batch_id": "batch",
                "status": "pending",
                "updated_at": "2026-05-28T00:00:00+00:00",
                "payload": {
                    "name": "Bioluminescent System",
                    "metadata": {
                        "recommendation": "inherit_variant",
                        "evolution_action": "inherit_variant",
                        "target_system_id": "system_target",
                        "dedupe_score": 0.66,
                    },
                    "related_existing_systems": [
                        {"system_id": "system_target", "name": "Oriental Fantasy Nature Sanctuary Art Direction"}
                    ],
                },
            }
        )

        self.assertEqual(summary["target_id"], "system_target")
        self.assertEqual(summary["target_name"], "Oriental Fantasy Nature Sanctuary Art Direction")

    def test_visual_asset_candidate_decide_rejects_legacy_actions(self):
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["visual-asset", "candidates", "decide", "candidate_style", "new_asset"])

        parsed = parser.parse_args(["visual-asset", "candidates", "decide", "candidate_style", "inherit_variant"])
        self.assertEqual(parsed.action, "inherit_variant")

    def test_context_compaction_entrypoints_parse(self):
        parser = build_parser()

        parsed = parser.parse_args(["prompt", "compose", "--source-prompt", "mist", "--debug-recall"])
        self.assertTrue(parsed.debug_recall)

        parsed = parser.parse_args(["visual-asset", "candidates", "compact", "--status", "confirmed"])
        self.assertEqual(parsed.status, "confirmed")

        parsed = parser.parse_args(["visual-asset", "evidence", "visual_asset_style", "--summary"])
        self.assertTrue(parsed.summary)

        parsed = parser.parse_args(["generation", "get", "generation_123", "--summary"])
        self.assertTrue(parsed.summary)

    def test_recall_status_is_active_only_with_explicit_admin_escape_hatch(self):
        parser = build_parser()

        parsed = parser.parse_args(["recall", "visual_asset", "--query", "mist", "--status", "active"])
        self.assertEqual(parsed.status, "active")
        self.assertFalse(parsed.include_unavailable)

        parsed = parser.parse_args(["recall", "visual_asset", "--query", "mist", "--include-unavailable"])
        self.assertTrue(parsed.include_unavailable)

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["recall", "visual_asset", "--query", "mist", "--status", "archived"])


if __name__ == "__main__":
    unittest.main()
