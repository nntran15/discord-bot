from __future__ import annotations

import logging

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
API_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"


def fetch_jobs(
    app_id: str,
    app_key: str,
    what: str = "software engineer",
    max_days_old: int = 1,
) -> list[Job]:
    if not app_id or not app_key:
        LOGGER.warning("Skipping Adzuna: missing ADZUNA_APP_ID or ADZUNA_APP_KEY")
        return []

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "max_days_old": max_days_old,
        "results_per_page": 50,
    }

    try:
        response = requests.get(API_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Adzuna fetch failed: %s", exc)
        return []

    jobs: list[Job] = []
    for result in payload.get("results", []):
        job_id = result.get("id")
        title = result.get("title")
        job_url = result.get("redirect_url")
        if not job_id or not title or not job_url:
            continue

        company_data = result.get("company") or {}
        jobs.append(
            Job(
                id=f"adzuna:{job_id}",
                title=title,
                company=company_data.get("display_name", "Unknown"),
                url=job_url,
                source="adzuna",
                posted_date=result.get("created", ""),
            )
        )

    return jobs