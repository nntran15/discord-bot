from __future__ import annotations

import logging
import re

import requests


LOGGER = logging.getLogger(__name__)
SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RESULTS_PER_REQUEST = 20
WORKDAY_URL_PATTERN = re.compile(
    r"^https://(?P<tenant>[a-z0-9-]+)\.(?P<pod>wd\d+)\.myworkdayjobs\.com/(?:[^/?#]+/)*(?P<site>[^/?#]+)/job/",
    re.IGNORECASE,
)
GREENHOUSE_URL_PATTERN = re.compile(
    r"^https://(?:boards|job-boards)\.greenhouse\.io/(?P<slug>[a-z0-9-]+)/jobs/\d+",
    re.IGNORECASE,
)
LEVER_URL_PATTERN = re.compile(
    r"^https://jobs\.lever\.co/(?P<slug>[a-z0-9-]+)/[a-f0-9-]+(?:/.*)?$",
    re.IGNORECASE,
)


def search(query: str, api_key: str, count: int = 50) -> list[dict]:
    if not api_key:
        LOGGER.warning("Skipping Workday discovery search: missing BRAVE_API_KEY")
        return []

    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }

    if count <= 0:
        return []

    results: list[dict] = []
    offset = 0
    remaining = count

    while remaining > 0:
        request_count = min(remaining, MAX_RESULTS_PER_REQUEST)
        params = {"q": query, "count": request_count, "offset": offset}

        try:
            response = requests.get(SEARCH_URL, params=params, headers=headers, timeout=20)
        except requests.RequestException as exc:
            LOGGER.warning("Brave search failed: %s", exc)
            return []

        if response.status_code in {401, 403, 429}:
            LOGGER.warning(
                "Brave Search API key invalid or credit exhausted (HTTP %s)",
                response.status_code,
            )
            return []

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("Brave search failed: %s", exc)
            return []

        payload = response.json()
        page_results = payload.get("web", {}).get("results", [])
        results.extend(page_results)

        remaining -= request_count
        offset += request_count

        if not payload.get("query", {}).get("more_results_available", False):
            break

    return results


def parse_workday_url(url: str) -> dict | None:
    match = WORKDAY_URL_PATTERN.match(url)
    if not match:
        return None

    return {
        "tenant": match.group("tenant"),
        "pod": match.group("pod"),
        "site": match.group("site"),
        "ats": "workday",
    }


def parse_greenhouse_url(url: str) -> dict | None:
    match = GREENHOUSE_URL_PATTERN.match(url)
    if not match:
        return None

    return {
        "tenant": match.group("slug"),
        "pod": "",
        "site": "",
        "ats": "greenhouse",
    }


def parse_lever_url(url: str) -> dict | None:
    match = LEVER_URL_PATTERN.match(url)
    if not match:
        return None

    return {
        "tenant": match.group("slug"),
        "pod": "",
        "site": "",
        "ats": "lever",
    }


def parse_discovered_source(url: str) -> dict | None:
    for parser in (parse_workday_url, parse_greenhouse_url, parse_lever_url):
        parsed = parser(url)
        if parsed:
            return parsed

    return None


def run_discovery(queries: list[str], api_key: str) -> list[dict]:
    discovered: list[dict] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for query in queries:
        for item in search(query, api_key):
            source = parse_discovered_source(item.get("url", ""))
            if not source:
                continue

            key = (
                source["ats"],
                source["tenant"],
                source["pod"],
                source["site"],
            )
            if key in seen_keys:
                continue

            seen_keys.add(key)
            discovered.append(source)

    return discovered