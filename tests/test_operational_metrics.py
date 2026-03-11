import unittest

from app.api.jobs import (
    _build_job_operational_summary,
    _summarize_excluded_reason_counts,
    _summarize_operational_metrics,
)
from app.api.schemas import JobCaptureSummary
from app.models import ScrapingJob


class OperationalMetricsTestCase(unittest.TestCase):
    def test_summarizes_excluded_reason_counts(self) -> None:
        counts = _summarize_excluded_reason_counts(
            [
                {"reason": "excluded_as_article"},
                {"reason": "excluded_as_article"},
                {"reason": "excluded_as_directory_seed:doctoralia"},
                {"reason": "duplicate_url"},
            ]
        )

        self.assertEqual(counts["excluded_as_article"], 2)
        self.assertEqual(counts["excluded_as_directory_seed:doctoralia"], 1)
        self.assertEqual(counts["duplicate_url"], 1)

    def test_builds_job_operational_summary(self) -> None:
        job = ScrapingJob(status="completed")
        capture_summary = JobCaptureSummary(
            accepted_count=2,
            candidates_processed=6,
            candidates_discovered=4,
            acceptance_rate=0.3333,
        )

        summary = _build_job_operational_summary(
            job=job,
            capture_summary=capture_summary,
            excluded_reason_counts={
                "excluded_as_article": 2,
                "excluded_as_directory_seed:doctoralia": 1,
            },
        )

        self.assertFalse(summary.completed_with_zero_accepted)
        self.assertEqual(summary.candidates_per_accepted, 3.0)
        self.assertEqual(summary.article_exclusion_count, 2)
        self.assertEqual(summary.directory_exclusion_count, 1)
        self.assertEqual(summary.article_directory_exclusion_ratio, 0.4286)

    def test_summarizes_operational_metrics_across_jobs(self) -> None:
        completed_zero_job = ScrapingJob(status="completed")
        completed_success_job = ScrapingJob(status="completed")

        response = _summarize_operational_metrics(
            [
                (
                    completed_zero_job,
                    JobCaptureSummary(
                        accepted_count=0,
                        candidates_processed=5,
                        candidates_discovered=5,
                        acceptance_rate=0.0,
                    ),
                    _build_job_operational_summary(
                        job=completed_zero_job,
                        capture_summary=JobCaptureSummary(
                            accepted_count=0,
                            candidates_processed=5,
                            candidates_discovered=5,
                            acceptance_rate=0.0,
                        ),
                        excluded_reason_counts={"excluded_as_article": 2},
                    ),
                ),
                (
                    completed_success_job,
                    JobCaptureSummary(
                        accepted_count=2,
                        candidates_processed=6,
                        candidates_discovered=4,
                        acceptance_rate=0.3333,
                    ),
                    _build_job_operational_summary(
                        job=completed_success_job,
                        capture_summary=JobCaptureSummary(
                            accepted_count=2,
                            candidates_processed=6,
                            candidates_discovered=4,
                            acceptance_rate=0.3333,
                        ),
                        excluded_reason_counts={"excluded_as_directory_seed:doctoralia": 1},
                    ),
                ),
            ]
        )

        self.assertEqual(response.total_jobs, 2)
        self.assertEqual(response.completed_jobs, 2)
        self.assertEqual(response.completed_jobs_with_zero_accepted, 1)
        self.assertEqual(response.completed_jobs_with_zero_accepted_ratio, 0.5)
        self.assertEqual(response.average_acceptance_rate, 0.1666)
        self.assertEqual(response.average_candidates_per_accepted, 3.0)
        self.assertEqual(response.total_article_exclusions, 2)
        self.assertEqual(response.total_directory_exclusions, 1)


if __name__ == "__main__":
    unittest.main()
