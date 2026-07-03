from __future__ import annotations

import hashlib
import json
import logging
import re
from urllib.parse import urlsplit, urlunsplit

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
JSONLD_PATTERN = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)


def fetch_all(urls: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for url in urls:
        try:
            job = fetch_job(url)
        except Exception as exc:
            LOGGER.warning("Custom job fetch failed for %s: %s", url, exc)
            continue

        if job:
            jobs.append(job)

    return jobs


def fetch_job(url: str) -> Job | None:
    normalized_url = _normalize_url(url)
    if not normalized_url:
        return None

    try:
        response = requests.get(normalized_url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        LOGGER.warning("Custom job fetch failed for %s: %s", normalized_url, exc)
        return None

    job_posting = _parse_jobposting_jsonld(response.text)
    if not job_posting:
        LOGGER.warning("Custom job fetch skipped for %s: missing JobPosting schema", normalized_url)
        return None

    title = str(job_posting.get("title") or "").strip()
    if not title:
        return None

    parsed_url = urlsplit(normalized_url)
    identifier = _job_identifier(job_posting, parsed_url.netloc, normalized_url)
    company = _company_name(job_posting, parsed_url.netloc)
    location = _format_job_location(job_posting.get("jobLocation"))

    return Job(
        id=f"custom:{parsed_url.netloc}:{identifier}",
        title=title,
        company=company,
        url=normalized_url,
        source="custom",
        posted_date=str(job_posting.get("datePosted") or "").strip(),
        location=location,
    )


def _normalize_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return ""

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _parse_jobposting_jsonld(html: str) -> dict | None:
    for raw_json in JSONLD_PATTERN.findall(html):
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        job_posting = _find_jobposting(parsed)
        if job_posting:
            return job_posting

    return None


def _find_jobposting(value: object) -> dict | None:
    if isinstance(value, dict):
        value_type = value.get("@type")
        if value_type == "JobPosting":
            return value
        if isinstance(value_type, list) and "JobPosting" in value_type:
            return value

        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                match = _find_jobposting(item)
                if match:
                    return match
        return None

    if isinstance(value, list):
        for item in value:
            match = _find_jobposting(item)
            if match:
                return match

    return None


def _job_identifier(job_posting: dict, host: str, normalized_url: str) -> str:
    identifier = job_posting.get("identifier")
    if isinstance(identifier, dict):
        value = str(identifier.get("value") or "").strip()
        if value:
            return value
    elif isinstance(identifier, str) and identifier.strip():
        return identifier.strip()

    digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]
    return f"{host}:{digest}"


def _company_name(job_posting: dict, host: str) -> str:
    hiring_organization = job_posting.get("hiringOrganization") or {}
    name = str(hiring_organization.get("name") or "").strip()
    if name:
        return name
    return host


def _format_job_location(job_location: dict | list | None) -> str:
    if isinstance(job_location, list):
        return "\n".join(part for part in (_format_job_location(item) for item in job_location) if part)

    if not isinstance(job_location, dict):
        return ""

    address = job_location.get("address")
    if isinstance(address, list):
        return "\n".join(part for part in (_format_address(item) for item in address) if part)

    if isinstance(address, dict):
        return _format_address(address)

    return ""


def _format_address(address: dict) -> str:
    parts = _dedupe_parts(
        [
            *_split_parts(str(address.get("addressLocality") or "")),
            *_split_parts(str(address.get("addressRegion") or "")),
            *_split_parts(_format_country(address.get("addressCountry"))),
        ]
    )
    return ", ".join(parts)


def _format_country(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or value.get("addressCountry") or "").strip()

    if isinstance(value, list):
        parts = [_format_country(item) for item in value]
        return ", ".join(_dedupe_parts([part for part in parts if part]))

    return str(value or "").strip()


def _dedupe_parts(parts: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = part.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)

    return deduped


def _split_parts(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]