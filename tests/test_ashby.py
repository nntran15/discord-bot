from __future__ import annotations

import unittest
from unittest.mock import patch

from sources import ashby


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class AshbySourceTests(unittest.TestCase):
    @patch("sources.ashby.requests.get")
    def test_fetch_jobs_reads_embedded_board_state_and_job_jsonld(self, mock_get) -> None:
        board_html = """
        <html><body><script>
        window.__ASHBY_STATE__ = {
            "organization": {"name": "Rundoo"},
            "jobBoard": {
                "jobPostings": [
                    {
                        "id": "c1fa53ea-dadf-4dcf-a144-f71bda03c9fa",
                        "title": "Software Engineer",
                        "isListed": true,
                        "publishedDate": "2026-06-03"
                    }
                ]
            }
        };
        </script></body></html>
        """
        job_html = """
        <html><head><script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Software Engineer",
            "datePosted": "2026-06-03",
            "employmentType": "FULL_TIME",
            "hiringOrganization": {"name": "Rundoo"},
            "jobLocation": {
                "address": {
                    "addressLocality": "Redwood City",
                    "addressRegion": "California",
                    "addressCountry": "USA"
                }
            },
            "identifier": {"value": "c1fa53ea-dadf-4dcf-a144-f71bda03c9fa"}
        }
        </script></head><body></body></html>
        """
        mock_get.side_effect = [FakeResponse(board_html), FakeResponse(job_html)]

        jobs = ashby.fetch_jobs("rundoo")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "ashby:rundoo:c1fa53ea-dadf-4dcf-a144-f71bda03c9fa")
        self.assertEqual(jobs[0].title, "Software Engineer")
        self.assertEqual(jobs[0].company, "Rundoo")
        self.assertEqual(jobs[0].url, "https://jobs.ashbyhq.com/rundoo/c1fa53ea-dadf-4dcf-a144-f71bda03c9fa")
        self.assertEqual(jobs[0].posted_date, "2026-06-03")
        self.assertEqual(jobs[0].location, "Redwood City, California, USA")


if __name__ == "__main__":
    unittest.main()