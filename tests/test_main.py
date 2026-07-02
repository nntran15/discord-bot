from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dedupe
import main
from sources.base import Job


def make_job(*, job_id: str, url: str) -> Job:
    job = Job(
        id=job_id,
        title="Junior Software Engineer",
        company="Example",
        url=url,
        source="greenhouse",
        posted_date="2026-07-02T11:50:00+00:00",
    )
    job.location = "San Francisco, CA"
    return job


class MainPipelineTests(unittest.TestCase):
    def test_main_deduplicates_equivalent_jobs_before_notifying(self) -> None:
        simplify_job = make_job(
            job_id="simplify:1",
            url="https://example.com/jobs/123?utm_source=Simplify&ref=Simplify",
        )
        source_job = make_job(
            job_id="greenhouse:1",
            url="https://example.com/jobs/123",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite"

            with (
                patch("main.parse_args", return_value=argparse.Namespace(dry_run=False)),
                patch("main.load_dotenv"),
                patch("main.init_db", side_effect=lambda: dedupe.init_db(str(db_path))),
                patch("main.load_companies", return_value={}),
                patch("main.load_filters", return_value=([], [])),
                patch("main.get_discovered_sources", return_value=[]),
                patch("main.greenhouse.fetch_all", return_value=[source_job]),
                patch("main.lever.fetch_all", return_value=[]),
                patch("main.adzuna.fetch_jobs", return_value=[]),
                patch("main.simplify_repo.fetch_jobs", return_value=[simplify_job]),
                patch("main.workday.fetch_all", return_value=[]),
                patch("main.filter_jobs", side_effect=lambda jobs, *_args, **_kwargs: jobs),
                patch("main.send_batch") as send_batch,
                patch(
                    "main.os.getenv",
                    side_effect=lambda key, default="": "https://discord.test/webhook"
                    if key == "DISCORD_WEBHOOK_URL"
                    else default,
                ),
            ):
                result = main.main()

        self.assertEqual(result, 0)
        send_batch.assert_called_once()
        sent_jobs = send_batch.call_args.args[0]
        self.assertEqual([job.id for job in sent_jobs], [source_job.id])

    def test_main_skips_job_if_equivalent_posting_was_already_seen(self) -> None:
        previously_seen_job = make_job(
            job_id="simplify:1",
            url="https://example.com/jobs/123?utm_source=Simplify&ref=Simplify",
        )
        source_job = make_job(
            job_id="greenhouse:1",
            url="https://example.com/jobs/123",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite"
            conn = dedupe.init_db(str(db_path))
            try:
                dedupe.mark_seen(conn, previously_seen_job)
            finally:
                conn.close()

            with (
                patch("main.parse_args", return_value=argparse.Namespace(dry_run=False)),
                patch("main.load_dotenv"),
                patch("main.init_db", side_effect=lambda: dedupe.init_db(str(db_path))),
                patch("main.load_companies", return_value={}),
                patch("main.load_filters", return_value=([], [])),
                patch("main.get_discovered_sources", return_value=[]),
                patch("main.greenhouse.fetch_all", return_value=[source_job]),
                patch("main.lever.fetch_all", return_value=[]),
                patch("main.adzuna.fetch_jobs", return_value=[]),
                patch("main.simplify_repo.fetch_jobs", return_value=[]),
                patch("main.workday.fetch_all", return_value=[]),
                patch("main.filter_jobs", side_effect=lambda jobs, *_args, **_kwargs: jobs),
                patch("main.send_batch") as send_batch,
                patch(
                    "main.os.getenv",
                    side_effect=lambda key, default="": "https://discord.test/webhook"
                    if key == "DISCORD_WEBHOOK_URL"
                    else default,
                ),
            ):
                result = main.main()

        self.assertEqual(result, 0)
        send_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()