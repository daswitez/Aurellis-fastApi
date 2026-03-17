import unittest

from app.api.jobs import (
    _compute_default_max_query_refinements,
    _filter_new_queries,
    _prepend_query_batches,
    _resolve_iteration_query_limit,
    _should_trigger_adaptive_refinement,
    _summarize_segment_window,
    _summarize_processed_window,
)


class AdaptiveJobsHelpersTestCase(unittest.TestCase):
    def test_default_max_query_refinements_scales_with_candidate_cap(self) -> None:
        self.assertEqual(_compute_default_max_query_refinements(25), 5)
        self.assertEqual(_compute_default_max_query_refinements(100), 10)

    def test_iteration_query_limit_uses_small_waves(self) -> None:
        self.assertEqual(
            _resolve_iteration_query_limit(
                iteration_index=0,
                max_candidates_to_process=25,
                target_accepted_results=5,
            ),
            6,
        )
        self.assertEqual(
            _resolve_iteration_query_limit(
                iteration_index=1,
                max_candidates_to_process=25,
                target_accepted_results=5,
            ),
            8,
        )

    def test_summarize_processed_window_tracks_noise_and_acceptance(self) -> None:
        stats = _summarize_processed_window(
            [
                {"acceptance_decision": "rejected_low_confidence", "rejection_reason": "geo_unknown"},
                {"acceptance_decision": "rejected_directory", "rejection_reason": "rejected_directory"},
                {"acceptance_decision": "accepted_target", "rejection_reason": None},
            ]
        )

        self.assertEqual(stats["processed_count"], 3)
        self.assertEqual(stats["accepted_target_delta"], 1)
        self.assertAlmostEqual(stats["noise_ratio"], 0.6667, places=4)

    def test_should_trigger_refinement_on_zero_accepted_or_queue_exhausted(self) -> None:
        should_refine, reason = _should_trigger_adaptive_refinement(
            window_stats={"processed_count": 10, "accepted_target_delta": 0, "noise_ratio": 0.2},
            candidate_queue_empty=False,
            refinement_window=10,
        )
        self.assertTrue(should_refine)
        self.assertEqual(reason, "low_acceptance_window")

        should_refine, reason = _should_trigger_adaptive_refinement(
            window_stats={"processed_count": 2, "accepted_target_delta": 1, "noise_ratio": 0.0},
            candidate_queue_empty=True,
            refinement_window=10,
        )
        self.assertTrue(should_refine)
        self.assertEqual(reason, "queue_exhausted")

    def test_should_trigger_refinement_from_serp_zero_recall_or_noise(self) -> None:
        should_refine, reason = _should_trigger_adaptive_refinement(
            window_stats={"processed_count": 2, "accepted_target_delta": 1, "noise_ratio": 0.0},
            candidate_queue_empty=False,
            refinement_window=10,
            search_evidence={
                "segment_performance": {
                    "coach_negocios": {"zero_result_queries": 2},
                }
            },
        )
        self.assertTrue(should_refine)
        self.assertEqual(reason, "segment_zero_recall")

        should_refine, reason = _should_trigger_adaptive_refinement(
            window_stats={"processed_count": 2, "accepted_target_delta": 1, "noise_ratio": 0.1},
            candidate_queue_empty=False,
            refinement_window=10,
            search_evidence={"queries_observed": 3, "current_wave_noise_ratio": 0.7},
        )
        self.assertTrue(should_refine)
        self.assertEqual(reason, "high_serp_noise")

    def test_filter_new_queries_dedupes_against_history(self) -> None:
        seen_queries = {"coaches españa"}
        filtered = _filter_new_queries(
            [
                ["coaches España", "site:instagram.com coach españa"],
                ["site:instagram.com coach españa", "marca personal españa"],
            ],
            seen_queries=seen_queries,
        )

        self.assertEqual(
            filtered,
            [["site:instagram.com coach españa"], ["marca personal españa"]],
        )

    def test_prepend_query_batches_prioritizes_refinements(self) -> None:
        query_batches, next_index = _prepend_query_batches(
            existing_batches=[["q1"], ["q2"], ["q3"]],
            next_batch_index=1,
            new_batches=[["refined-1"], ["refined-2"]],
        )

        self.assertEqual(query_batches, [["refined-1"], ["refined-2"], ["q2"], ["q3"]])
        self.assertEqual(next_index, 0)

    def test_segment_summary_accepts_query_reports_after_processed_stats_exist(self) -> None:
        summary = _summarize_segment_window(
            [
                {
                    "segment_id": "coach_negocios",
                    "query": "coach de negocios espana",
                    "query_platform": "website",
                    "acceptance_decision": "rejected_low_confidence",
                    "rejection_reason": "low_contact_quality",
                    "quality_status": "rejected",
                    "location_match_status": "match",
                    "language_match_status": "match",
                    "domain": "example.com",
                    "query_family": "website_validation_queries",
                }
            ],
            [
                {
                    "segment_id": "coach_negocios",
                    "query": "coach de negocios espana",
                    "platform": "website",
                    "returned_count": 0,
                    "kept_count": 0,
                    "zero_results": True,
                    "excluded_reason_counts": {},
                }
            ],
        )

        stats = summary["segment_performance"]["coach_negocios"]
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["query_count"], 1)
        self.assertEqual(stats["zero_result_queries"], 1)


if __name__ == "__main__":
    unittest.main()
