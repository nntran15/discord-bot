from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
API_URL = "https://api.lever.co/v0/postings/{company_slug}"


def _company_name(company_slug: str) -> str:
    return company_slug.replace("-", " ").title()


def _format_timestamp(raw_timestamp: int | str | None) -> str:
    if raw_timestamp in (None, ""):
        return ""

    try:
        timestamp = int(raw_timestamp)
    except (TypeError, ValueError):
        return str(raw_timestamp)

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def fetch_jobs(company_slug: str) -> list[Job]:
    try:
        response = requests.get(API_URL.format(company_slug=company_slug), timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Lever fetch failed for %s: %s", company_slug, exc)
        return []

    jobs: list[Job] = []
    for posting in payload:
        job_id = posting.get("id")
        title = posting.get("text")
        job_url = posting.get("hostedUrl") or posting.get("applyUrl")
        if not job_id or not title or not job_url:
            continue

        jobs.append(
            Job(
                id=f"lever:{company_slug}:{job_id}",
                title=title,
                company=_company_name(company_slug),
                url=job_url,
                source="lever",
                posted_date=_format_timestamp(posting.get("createdAt")),
            )
        )

    return jobs


def fetch_all(company_slugs: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for company_slug in company_slugs:
        try:
            jobs.extend(fetch_jobs(company_slug))
        except Exception as exc:
            LOGGER.warning("Lever fetch failed for %s: %s", company_slug, exc)
    return jobs