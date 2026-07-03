from __future__ import annotations

import json
import logging
import re

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
BOARD_URL = "https://jobs.ashbyhq.com/{company_slug}"
JOB_URL = "https://jobs.ashbyhq.com/{company_slug}/{job_id}"
EMBEDDED_STATE_PATTERN = re.compile(r"window\.__[^=]*\s*=\s*(\{.*?\});", re.S)
JSONLD_PATTERN = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)


def fetch_jobs(company_slug: str) -> list[Job]:
    try:
        response = requests.get(BOARD_URL.format(company_slug=company_slug), timeout=20)
        response.raise_for_status()
        board_state = _parse_board_state(response.text)
    except Exception as exc:
        LOGGER.warning("Ashby fetch failed for %s: %s", company_slug, exc)
        return []

    organization = board_state.get("organization") or {}
    company_name = str(organization.get("name") or company_slug.replace("-", " ").title())
    postings = (board_state.get("jobBoard") or {}).get("jobPostings") or []

    jobs: list[Job] = []
    for posting in postings:
        if not posting.get("isListed", True):
            continue

        job = _fetch_job(company_slug, company_name, posting)
        if job:
            jobs.append(job)

    return jobs


def fetch_all(company_slugs: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for company_slug in company_slugs:
        try:
            jobs.extend(fetch_jobs(company_slug))
        except Exception as exc:
            LOGGER.warning("Ashby fetch failed for %s: %s", company_slug, exc)
    return jobs


def _parse_board_state(html: str) -> dict:
    match = EMBEDDED_STATE_PATTERN.search(html)
    if not match:
        raise ValueError("Ashby board page missing embedded state")

    return json.loads(match.group(1))


def _fetch_job(company_slug: str, company_name: str, posting: dict) -> Job | None:
    posting_id = str(posting.get("id") or "")
    title = str(posting.get("title") or "")
    if not posting_id or not title:
        return None

    job_url = JOB_URL.format(company_slug=company_slug, job_id=posting_id)
    detail = _fetch_job_detail(job_url)
    location = _format_job_location(detail.get("jobLocation")) if detail else _fallback_location(posting)
    job_title = str(detail.get("title") or title) if detail else title
    posted_date = str(detail.get("datePosted") or posting.get("publishedDate") or "") if detail else str(
        posting.get("publishedDate") or ""
    )
    detail_company = _detail_company_name(detail)

    return Job(
        id=f"ashby:{company_slug}:{posting_id}",
        title=job_title,
        company=detail_company or company_name,
        url=job_url,
        source="ashby",
        posted_date=posted_date,
        location=location,
    )


def _fetch_job_detail(job_url: str) -> dict | None:
    try:
        response = requests.get(job_url, timeout=20)
        response.raise_for_status()
    except Exception:
        return None

    for raw_json in JSONLD_PATTERN.findall(response.text):
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
            continue

        if isinstance(parsed, dict) and parsed.get("@type") == "JobPosting":
            return parsed

    return None


def _detail_company_name(detail: dict | None) -> str:
    if not detail:
        return ""

    hiring_organization = detail.get("hiringOrganization") or {}
    return str(hiring_organization.get("name") or "")


def _format_job_location(job_location: dict | list | None) -> str:
    if isinstance(job_location, list):
        parts = [_format_job_location(item) for item in job_location]
        return "\n".join(part for part in parts if part)

    if not isinstance(job_location, dict):
        return ""

    address = job_location.get("address") or {}
    locality = str(address.get("addressLocality") or "").strip()
    region = str(address.get("addressRegion") or "").strip()
    country = str(address.get("addressCountry") or "").strip()
    components = [value for value in (locality, region, country) if value]
    return ", ".join(components)


def _fallback_location(posting: dict) -> str:
    primary = str(posting.get("locationExternalName") or posting.get("locationName") or "").strip()
    secondary_locations = []
    for secondary in posting.get("secondaryLocations") or []:
        name = str(secondary.get("locationExternalName") or secondary.get("locationName") or "").strip()
        country = str(
            (((secondary.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or "")
        ).strip()
        parts = [value for value in (name, country) if value]
        if parts:
            secondary_locations.append(", ".join(parts))

    locations = [value for value in [primary, *secondary_locations] if value]
    return "\n".join(locations)