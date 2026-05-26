import unittest

from aether_core.similarity import compare_profiles, decision_for_score


class SimilarityTests(unittest.TestCase):
    def test_compare_profiles_scores_matching_fields(self):
        weights = {
            "artStyle": 0.5,
            "lighting": 0.25,
            "mood": 0.25,
        }
        source = {
            "art_style": "cinematic cyberpunk illustration",
            "lighting": "low key neon rim light",
            "mood": ["lonely", "nostalgic"],
        }
        candidate = {
            "art_style": "cinematic cyberpunk illustration",
            "lighting": "neon rim light at night",
            "mood": ["lonely", "distant"],
        }

        result = compare_profiles(source, candidate, weights)

        self.assertGreater(result["similarity_score"], 0.45)
        self.assertIn("art_style", result["matched_dimensions"])

    def test_decision_for_score(self):
        thresholds = {"existingStyle": 0.86, "styleBranch": 0.72}

        self.assertEqual(decision_for_score(0.9, thresholds), "existing_style")
        self.assertEqual(decision_for_score(0.8, thresholds), "style_branch")
        self.assertEqual(decision_for_score(0.5, thresholds), "new_style")


if __name__ == "__main__":
    unittest.main()

