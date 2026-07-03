from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit, urlunsplit

import requests


LOGGER = logging.getLogger(__name__)
SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RESULTS_PER_REQUEST = 20
MAX_QUERY_CHARS = 400
MAX_QUERY_WORDS = 50
MAX_OFFSET = 9
QUERY_WORD_PATTERN = re.compile(r"\S+")
PERMANENT_INVALID_SOURCE_STATUSES = {404, 410, 422}
WORKDAY_VALIDATION_BODY = {
    "appliedFacets": {},
    "limit": 1,
    "offset": 0,
    "searchText": "software engineer",
}
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
ASHBY_URL_PATTERN = re.compile(
    r"^https://jobs\.ashbyhq\.com/(?P<slug>[a-z0-9-]+)/(?P<job_id>[a-f0-9-]{36})(?:/application)?(?:\?.*)?$",
    re.IGNORECASE,
)
CUSTOM_HOST_SKIP_PATTERNS = (
    re.compile(r"(?:^|\.)myworkdayjobs\.com$", re.IGNORECASE),
    re.compile(r"(?:^|\.)greenhouse\.io$", re.IGNORECASE),
    re.compile(r"(?:^|\.)lever\.co$", re.IGNORECASE),
    re.compile(r"(?:^|\.)ashbyhq\.com$", re.IGNORECASE),
)
JSONLD_PATTERN = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)


def search(query: str, api_key: str, count: int = 50) -> list[dict]:
    if not api_key:
        LOGGER.warning("Skipping Workday discovery search: missing BRAVE_API_KEY")
        return []

    word_count = _query_word_count(query)
    if len(query) > MAX_QUERY_CHARS or word_count > MAX_QUERY_WORDS:
        LOGGER.warning(
            "Skipping Brave search query exceeding API limits (chars=%s, words=%s)",
            len(query),
            word_count,
        )
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

    while remaining > 0 and offset <= MAX_OFFSET:
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
        if response.status_code == 422:
            LOGGER.warning(
                "Brave search rejected query (chars=%s, words=%s, offset=%s)",
                len(query),
                word_count,
                offset,
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
        offset += 1

        if not payload.get("query", {}).get("more_results_available", False):
            break

    return results


def _query_word_count(query: str) -> int:
    return len(QUERY_WORD_PATTERN.findall(query))


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


def parse_ashby_url(url: str) -> dict | None:
    match = ASHBY_URL_PATTERN.match(url)
    if not match:
        return None

    return {
        "tenant": match.group("slug"),
        "pod": "",
        "site": "",
        "ats": "ashby",
    }


def parse_custom_source(url: str) -> dict | None:
    normalized_url = _normalize_custom_url(url)
    if not normalized_url:
        return None

    parsed_url = urlsplit(normalized_url)
    if any(pattern.search(parsed_url.netloc) for pattern in CUSTOM_HOST_SKIP_PATTERNS):
        return None

    try:
        response = requests.get(normalized_url, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None

    if not _has_jobposting_jsonld(response.text):
        return None

    return {
        "tenant": parsed_url.netloc,
        "pod": "",
        "site": normalized_url,
        "ats": "custom",
    }


def parse_discovered_source(url: str) -> dict | None:
    for parser in (parse_workday_url, parse_greenhouse_url, parse_lever_url, parse_ashby_url):
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
                source = parse_custom_source(item.get("url", ""))
            if not source:
                continue
            if not is_valid_source(source):
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


def is_valid_source(source: dict) -> bool:
    ats = source.get("ats", "")
    if ats == "custom":
        return True

    try:
        response = _validate_source(source)
    except requests.RequestException as exc:
        LOGGER.warning("Source validation failed for %s: %s", _source_label(source), exc)
        return True

    if response.status_code in PERMANENT_INVALID_SOURCE_STATUSES:
        LOGGER.info("Skipping invalid discovered source: %s", _source_label(source))
        return False

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("Source validation failed for %s: %s", _source_label(source), exc)

    return True


def _validate_source(source: dict) -> requests.Response:
    ats = source.get("ats", "")
    tenant = source.get("tenant", "")
    pod = source.get("pod", "")
    site = source.get("site", "")

    if ats == "greenhouse":
        return requests.get(f"https://boards-api.greenhouse.io/v1/boards/{tenant}/jobs", timeout=20)
    if ats == "lever":
        return requests.get(f"https://api.lever.co/v0/postings/{tenant}", timeout=20)
    if ats == "ashby":
        return requests.get(f"https://jobs.ashbyhq.com/{tenant}", timeout=20)
    if ats == "workday":
        return requests.post(
            f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
            json=WORKDAY_VALIDATION_BODY,
            timeout=20,
        )

    return requests.Response()


def _source_label(source: dict) -> str:
    ats = source.get("ats", "")
    tenant = source.get("tenant", "")
    pod = source.get("pod", "")
    site = source.get("site", "")
    return "/".join(part for part in (ats, tenant, pod, site) if part)


def _normalize_custom_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return ""

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _has_jobposting_jsonld(html: str) -> bool:
    for raw_json in JSONLD_PATTERN.findall(html):
        if '"JobPosting"' in raw_json or "'JobPosting'" in raw_json:
            return True

    return False