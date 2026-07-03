from __future__ import annotations

from pathlib import Path
import re
import unittest
from unittest.mock import patch

import requests
import yaml

import discovery


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> dict:
        return self._payload


class DiscoverySearchTests(unittest.TestCase):
    @patch("discovery.requests.get")
    def test_search_paginates_when_count_exceeds_brave_limit(self, mock_get) -> None:
        mock_get.side_effect = [
            FakeResponse(
                200,
                {
                    "web": {"results": [{"url": "https://example.com/1"}]},
                    "query": {"more_results_available": True},
                },
            ),
            FakeResponse(
                200,
                {
                    "web": {"results": [{"url": "https://example.com/2"}]},
                    "query": {"more_results_available": True},
                },
            ),
            FakeResponse(
                200,
                {
                    "web": {"results": [{"url": "https://example.com/3"}]},
                    "query": {"more_results_available": False},
                },
            ),
        ]

        results = discovery.search("site:myworkdayjobs.com junior software engineer", "token", count=50)

        self.assertEqual(
            results,
            [
                {"url": "https://example.com/1"},
                {"url": "https://example.com/2"},
                {"url": "https://example.com/3"},
            ],
        )
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"]["count"], 20)
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"]["offset"], 0)
        self.assertEqual(mock_get.call_args_list[1].kwargs["params"]["count"], 20)
        self.assertEqual(mock_get.call_args_list[1].kwargs["params"]["offset"], 1)
        self.assertEqual(mock_get.call_args_list[2].kwargs["params"]["count"], 10)
        self.assertEqual(mock_get.call_args_list[2].kwargs["params"]["offset"], 2)

    @patch("discovery.requests.get")
    def test_search_skips_queries_that_exceed_brave_limits(self, mock_get) -> None:
        query = "word " * 51

        results = discovery.search(query.strip(), "token")

        self.assertEqual(results, [])
        mock_get.assert_not_called()

    def test_discovery_queries_fit_brave_limits(self) -> None:
        config_path = Path("config/discovery_queries.yaml")
        queries = yaml.safe_load(config_path.read_text(encoding="utf-8"))["queries"]

        for query in queries:
            with self.subTest(query=query):
                self.assertLessEqual(len(query), 400)
                self.assertLessEqual(len(re.findall(r"\S+", query)), 50)

    @patch("discovery.requests.post")
    @patch("discovery.search")
    def test_run_discovery_skips_permanently_invalid_workday_source(self, mock_search, mock_post) -> None:
        mock_search.return_value = [
            {
                "url": "https://scientificgames.wd5.myworkdayjobs.com/en-US/LightWonderExternalCareers/job/test"
            }
        ]
        mock_post.return_value = FakeResponse(422, {})

        sources = discovery.run_discovery(["query"], "token")

        self.assertEqual(sources, [])

    def test_parse_discovered_source_supports_greenhouse_url(self) -> None:
        source = discovery.parse_discovered_source("https://boards.greenhouse.io/twilio/jobs/3409275")

        self.assertEqual(
            source,
            {
                "tenant": "twilio",
                "pod": "",
                "site": "",
                "ats": "greenhouse",
            },
        )

    def test_parse_discovered_source_supports_job_boards_greenhouse_url(self) -> None:
        source = discovery.parse_discovered_source("https://job-boards.greenhouse.io/xai/jobs/5179367007")

        self.assertEqual(
            source,
            {
                "tenant": "xai",
                "pod": "",
                "site": "",
                "ats": "greenhouse",
            },
        )

    def test_parse_discovered_source_supports_lever_url(self) -> None:
        source = discovery.parse_discovered_source(
            "https://jobs.lever.co/whoop/3b94218d-3a5a-4dd1-91c7-5f18655c93a8"
        )

        self.assertEqual(
            source,
            {
                "tenant": "whoop",
                "pod": "",
                "site": "",
                "ats": "lever",
            },
        )

    def test_parse_discovered_source_supports_ashby_url(self) -> None:
        source = discovery.parse_discovered_source(
            "https://jobs.ashbyhq.com/rundoo/c1fa53ea-dadf-4dcf-a144-f71bda03c9fa/application?src=linkedin"
        )

        self.assertEqual(
            source,
            {
                "tenant": "rundoo",
                "pod": "",
                "site": "",
                "ats": "ashby",
            },
        )

    @patch("discovery.search")
    @patch("discovery.requests.get")
    def test_run_discovery_supports_custom_jobposting_pages(self, mock_get, mock_search) -> None:
        mock_search.return_value = [
            {
                "url": "https://jobs.northropgrumman.com/careers/job/1340072643008?code=JB-18202&rx_job=R10238678"
            }
        ]
        mock_get.return_value = FakeResponse(
            200,
            {},
            text='''<html><head><script type="application/ld+json">{"@context":"http://schema.org","@type":"JobPosting","title":"Software Engineer","datePosted":"2026-07-01T00:00:00"}</script></head></html>''',
        )

        sources = discovery.run_discovery(["custom query"], "token")

        self.assertEqual(
            sources,
            [
                {
                    "tenant": "jobs.northropgrumman.com",
                    "pod": "",
                    "site": "https://jobs.northropgrumman.com/careers/job/1340072643008?code=JB-18202&rx_job=R10238678",
                    "ats": "custom",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()