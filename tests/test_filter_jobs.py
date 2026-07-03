from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from filter_jobs import filter_jobs, load_filters
from sources.base import Job


class FilterJobsTests(unittest.TestCase):
    def test_filter_jobs_keeps_only_recent_us_jobs(self) -> None:
        now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        include_patterns = [r"\bjunior\b", r"\bsoftware engineer\s*i\b"]

        recent_us_job = Job(
            id="greenhouse:1",
            title="Junior Software Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            source="greenhouse",
            posted_date=(now - timedelta(minutes=15)).isoformat(),
        )
        recent_us_job.location = "San Francisco, CA"

        recent_foreign_job = Job(
            id="simplify:2",
            title="Junior Software Engineer",
            company="Example",
            url="https://example.com/jobs/2",
            source="simplify",
            posted_date="15m",
        )
        recent_foreign_job.location = "Toronto, ON, Canada"

        stale_us_job = Job(
            id="lever:3",
            title="Junior Software Engineer",
            company="Example",
            url="https://example.com/jobs/3",
            source="lever",
            posted_date=(now - timedelta(days=8)).isoformat(),
        )
        stale_us_job.location = "New York, NY"

        same_day_job = Job(
            id="workday:4",
            title="Software Engineer I",
            company="Example",
            url="https://example.com/jobs/4",
            source="workday",
            posted_date="Posted Today",
        )
        same_day_job.location = "Austin, TX"

        week_old_job = Job(
            id="workday:5",
            title="Software Engineer I",
            company="Example",
            url="https://example.com/jobs/5",
            source="workday",
            posted_date="Posted 7 Days Ago",
        )
        week_old_job.location = "El Segundo, CA"

        filtered = filter_jobs(
            [recent_us_job, recent_foreign_job, stale_us_job, same_day_job, week_old_job],
            include_patterns,
            [],
            now=now,
        )

        self.assertEqual([job.id for job in filtered], [recent_us_job.id, same_day_job.id, week_old_job.id])

    def test_default_filters_match_coop_and_early_career_titles(self) -> None:
        now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        include_patterns, exclude_patterns = load_filters(
            "c:\\Users\\Nathan\\Desktop\\Personal\\Programming\\Discord Bot\\job-alert-bot\\config\\filters.yaml"
        )

        coop_job = Job(
            id="workday:coop",
            title="Software Engineering Co-op Spring 2027",
            company="Example",
            url="https://example.com/jobs/coop",
            source="workday",
            posted_date="Posted Yesterday",
            location="USA, Louisville, KY",
        )
        early_career_job = Job(
            id="workday:early-career",
            title="Avionics Software (Embedded) Engineer I - Early Career - 2026 Starts",
            company="Example",
            url="https://example.com/jobs/early-career",
            source="workday",
            posted_date="Posted Today",
            location="Greater Seattle Area, USA",
        )

        filtered = filter_jobs([coop_job, early_career_job], include_patterns, exclude_patterns, now=now)

        self.assertEqual([job.id for job in filtered], [coop_job.id, early_career_job.id])

    def test_default_filters_match_ncg_software_titles(self) -> None:
        now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        include_patterns, exclude_patterns = load_filters(
            "c:\\Users\\Nathan\\Desktop\\Personal\\Programming\\Discord Bot\\job-alert-bot\\config\\filters.yaml"
        )

        ncg_job = Job(
            id="custom:ncg",
            title="2026 NCG - Software Engineer, BS/MS",
            company="Applied Materials",
            url="https://jobs.appliedmaterials.com/job/-/-/95/94623970944",
            source="custom",
            posted_date="2026-07-02",
            location="Santa Clara, CA",
        )

        filtered = filter_jobs([ncg_job], include_patterns, exclude_patterns, now=now)

        self.assertEqual([job.id for job in filtered], [ncg_job.id])


if __name__ == "__main__":
    unittest.main()