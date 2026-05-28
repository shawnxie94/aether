import contextlib
import io
import unittest

from aether_core.cli import build_parser, visual_asset_candidate_summary


class CliTests(unittest.TestCase):
    def test_visual_asset_candidate_summary_uses_evolution_fields(self):
        summary = visual_asset_candidate_summary(
            {
                "id": "candidate_style",
                "batch_id": "batch",
                "type": "style",
                "name": "Painterly Style",
                "reuse_score": 0.74,
                "decision": "asset_variant",
                "target_asset_id": "legacy_target",
                "similar_candidates": [{"asset_id": "target_asset"}],
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
                "decision": "new_asset",
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

    def test_visual_asset_candidate_decide_rejects_legacy_actions(self):
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["visual-asset", "candidates", "decide", "candidate_style", "new_asset"])

        parsed = parser.parse_args(["visual-asset", "candidates", "decide", "candidate_style", "inherit_variant"])
        self.assertEqual(parsed.action, "inherit_variant")


if __name__ == "__main__":
    unittest.main()
