import unittest

from app.api.jobs import (
    _summarize_commercial_metrics,
    _summarize_commercial_usage,
    COMMERCIAL_ROLLOUT_LAYERS,
    COMMERCIAL_ROLLOUT_STAGE,
)
from app.models import ScrapingJob


class CommercialMetricsTestCase(unittest.TestCase):
    def test_summarizes_commercial_usage(self) -> None:
        summary = _summarize_commercial_usage(
            [
                ("accepted_target", "consistent", {"invalid_phone_candidates_count": 2}),
                ("accepted_related", "consistent", {"phone_validation_rejections": {"sequence_noise": 1}}),
                ("rejected_directory", "unknown", None),
                ("rejected_media", "inconsistent", {"invalid_phone_candidates_count": 1}),
            ]
        )

        self.assertEqual(summary.accepted_target_count, 1)
        self.assertEqual(summary.accepted_related_count, 1)
        self.assertEqual(summary.rejected_non_target_count, 2)
        self.assertEqual(summary.inconsistent_contact_count, 1)
        self.assertEqual(summary.false_phone_filtered_count, 4)
        self.assertEqual(summary.accepted_target_precision, 0.5)

    def test_summarizes_commercial_metrics_across_jobs(self) -> None:
        first_job = ScrapingJob(status="completed", total_processed=5)
        second_job = ScrapingJob(status="completed", total_processed=3)

        response = _summarize_commercial_metrics(
            [
                (
                    first_job,
                    _summarize_commercial_usage(
                        [
                            ("accepted_target", "consistent", {"invalid_phone_candidates_count": 2}),
                            ("accepted_related", "inconsistent", {"invalid_phone_candidates_count": 1}),
                            ("rejected_directory", "unknown", None),
                        ]
                    ),
                ),
                (
                    second_job,
                    _summarize_commercial_usage(
                        [
                            ("accepted_target", "consistent", None),
                            ("rejected_article", "unknown", {"phone_validation_rejections": {"date_like": 1}}),
                        ]
                    ),
                ),
            ]
        )

        self.assertEqual(response.total_jobs, 2)
        self.assertEqual(response.total_results_processed, 8)
        self.assertEqual(response.total_accepted_target, 2)
        self.assertEqual(response.total_accepted_related, 1)
        self.assertEqual(response.total_rejected_non_target, 2)
        self.assertEqual(response.accepted_non_target_rate, 0.125)
        self.assertEqual(response.inconsistent_contact_count, 1)
        self.assertEqual(response.inconsistent_contact_rate, 0.125)
        self.assertEqual(response.false_phone_filtered_count, 4)
        self.assertEqual(response.false_phone_filtered_rate, 0.5)
        self.assertEqual(response.accepted_target_precision, 0.6667)
        self.assertEqual(response.rollout_stage, COMMERCIAL_ROLLOUT_STAGE)
        self.assertEqual(response.rollout_layers_completed, COMMERCIAL_ROLLOUT_LAYERS)


if __name__ == "__main__":
    unittest.main()
