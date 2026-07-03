from __future__ import annotations

import unittest
from unittest.mock import patch

from sources import custom_site


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class CustomSiteSourceTests(unittest.TestCase):
    @patch("sources.custom_site.requests.get")
    def test_fetch_jobs_reads_jobposting_jsonld(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(
            '''
            <html><head>
            <script type="application/ld+json">
            {
                "@context": "http://schema.org",
                "@type": "JobPosting",
                "title": "2026 NCG - Software Engineer, BS/MS",
                "datePosted": "2026-07-02",
                "hiringOrganization": {"name": "Applied Materials"},
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "Santa Clara",
                        "addressRegion": "CA",
                        "addressCountry": "USA"
                    }
                },
                "identifier": {"name": "Applied Materials", "value": "R2619063"}
            }
            </script>
            </head><body></body></html>
            '''
        )

        jobs = custom_site.fetch_all(["https://jobs.appliedmaterials.com/job/-/-/95/94623970944"])

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "custom:jobs.appliedmaterials.com:R2619063")
        self.assertEqual(jobs[0].title, "2026 NCG - Software Engineer, BS/MS")
        self.assertEqual(jobs[0].company, "Applied Materials")
        self.assertEqual(jobs[0].url, "https://jobs.appliedmaterials.com/job/-/-/95/94623970944")
        self.assertEqual(jobs[0].posted_date, "2026-07-02")
        self.assertEqual(jobs[0].location, "Santa Clara, CA, USA")

    @patch("sources.custom_site.requests.get")
    def test_fetch_jobs_formats_nested_country_metadata(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(
            '''
            <html><head>
            <script type="application/ld+json">
            {
                "@context": "http://schema.org",
                "@type": "JobPosting",
                "title": "Software Engineer (AHT)",
                "datePosted": "2026-07-01T00:00:00",
                "hiringOrganization": {"name": "Northrop Grumman"},
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "Manhattan Beach",
                        "addressRegion": "CA,US",
                        "addressCountry": {"@type": "Country", "name": "US"}
                    }
                }
            }
            </script>
            </head><body></body></html>
            '''
        )

        jobs = custom_site.fetch_all(["https://jobs.northropgrumman.com/careers/job/1340072643008"])

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Manhattan Beach, CA, US")


if __name__ == "__main__":
    unittest.main()