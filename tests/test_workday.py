from __future__ import annotations

import unittest
from unittest.mock import patch

from sources import workday


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class WorkdaySourceTests(unittest.TestCase):
    @patch("sources.workday.requests.post")
    def test_fetch_jobs_uses_public_workday_site_prefix_in_urls(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            {
                "jobPostings": [
                    {
                        "title": "Associate Software Engineer",
                        "externalPath": "/job/USA---Maryland-Heights-MO/Associate-Software-Engineer_JR2026516673-1",
                        "locationsText": "USA, Maryland Heights, MO",
                        "postedOn": "Posted Today",
                    }
                ]
            }
        )

        jobs = workday.fetch_jobs_for_tenant("boeing", "wd1", "EXTERNAL_CAREERS")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            jobs[0].url,
            "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS/job/USA---Maryland-Heights-MO/Associate-Software-Engineer_JR2026516673-1",
        )


if __name__ == "__main__":
    unittest.main()