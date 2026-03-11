import unittest

from app.services.scoring import build_final_score


class ScoringStrategyTestCase(unittest.TestCase):
    def test_uses_heuristic_only_when_ai_is_not_selected(self) -> None:
        result = build_final_score(
            ai_data={},
            ai_trace={"selected_method": "heuristic"},
            heuristic_data={
                "score": 0.52,
                "confidence_level": "medium",
                "fit_summary": "Fit heuristico moderado; destacan contactabilidad, madurez digital.",
            },
        )

        self.assertEqual(result["score"], 0.52)
        self.assertEqual(result["confidence_level"], "medium")
        self.assertEqual(result["scoring_trace"]["strategy"], "heuristic_only")
        self.assertEqual(result["scoring_trace"]["heuristic_weight"], 1.0)
        self.assertEqual(result["fit_summary"], "Fit heuristico moderado; destacan contactabilidad, madurez digital.")

    def test_blends_ai_and_heuristic_scores_with_confidence_weighting(self) -> None:
        result = build_final_score(
            ai_data={"score": 0.8, "confidence_level": "high"},
            ai_trace={"selected_method": "ai"},
            heuristic_data={
                "score": 0.7,
                "confidence_level": "medium",
                "fit_summary": "Fit heuristico fuerte; destacan intencion comercial, stack.",
            },
        )

        self.assertEqual(result["scoring_trace"]["strategy"], "hybrid")
        self.assertEqual(result["scoring_trace"]["ai_weight"], 0.85)
        self.assertEqual(result["scoring_trace"]["heuristic_weight"], 0.15)
        self.assertEqual(result["scoring_trace"]["agreement_band"], "high")
        self.assertEqual(result["score"], 0.785)
        self.assertEqual(result["confidence_level"], "high")
        self.assertIn("IA y heuristica son consistentes", result["fit_summary"])


if __name__ == "__main__":
    unittest.main()
