from __future__ import annotations

import logging

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
API_URL = "https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"


def _company_name(company_slug: str) -> str:
    return company_slug.replace("-", " ").title()


def fetch_jobs(company_slug: str) -> list[Job]:
    try:
        response = requests.get(API_URL.format(company_slug=company_slug), timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Greenhouse fetch failed for %s: %s", company_slug, exc)
        return []

    jobs: list[Job] = []
    for posting in payload.get("jobs", []):
        job_id = posting.get("id")
        title = posting.get("title")
        job_url = posting.get("absolute_url")
        if not job_id or not title or not job_url:
            continue

        jobs.append(
            Job(
                id=f"greenhouse:{company_slug}:{job_id}",
                title=title,
                company=_company_name(company_slug),
                url=job_url,
                source="greenhouse",
                posted_date=posting.get("updated_at", ""),
            )
        )

    return jobs


def fetch_all(company_slugs: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for company_slug in company_slugs:
        try:
            jobs.extend(fetch_jobs(company_slug))
        except Exception as exc:
            LOGGER.warning("Greenhouse fetch failed for %s: %s", company_slug, exc)
    return jobs