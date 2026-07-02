from __future__ import annotations

import logging

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
API_URL = "https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"


def _company_name(tenant: str) -> str:
    return tenant.replace("-", " ").title()


def fetch_jobs_for_tenant(
    tenant: str,
    pod: str,
    site: str,
    search_text: str = "software engineer",
) -> list[Job]:
    body = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": search_text,
    }

    try:
        response = requests.post(
            API_URL.format(tenant=tenant, pod=pod, site=site),
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        LOGGER.warning("Workday fetch failed for %s/%s/%s: %s", tenant, pod, site, exc)
        return []

    jobs: list[Job] = []
    for posting in payload.get("jobPostings", []):
        external_path = posting.get("externalPath")
        title = posting.get("title")
        if not external_path or not title:
            continue

        jobs.append(
            Job(
                id=f"workday:{tenant}:{external_path}",
                title=title,
                company=_company_name(tenant),
                url=f"https://{tenant}.{pod}.myworkdayjobs.com{external_path}",
                source="workday",
                posted_date=posting.get("postedOn", ""),
                location=str(posting.get("locationsText") or ""),
            )
        )

    return jobs


def fetch_all(discovered_sources: list[dict]) -> list[Job]:
    jobs: list[Job] = []
    for source in discovered_sources:
        try:
            jobs.extend(
                fetch_jobs_for_tenant(
                    tenant=source["tenant"],
                    pod=source["pod"],
                    site=source["site"],
                )
            )
        except Exception as exc:
            LOGGER.warning(
                "Workday fetch failed for %s/%s/%s: %s",
                source.get("tenant"),
                source.get("pod"),
                source.get("site"),
                exc,
            )
    return jobs