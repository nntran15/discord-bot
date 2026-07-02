from __future__ import annotations

import logging
import time

import requests

from sources.base import Job


LOGGER = logging.getLogger(__name__)


def _chunk_jobs(jobs: list[Job], batch_size: int) -> list[list[Job]]:
    return [jobs[index : index + batch_size] for index in range(0, len(jobs), batch_size)]


def _build_embed(job: Job) -> dict:
    return {
        "title": job.title[:256],
        "url": job.url,
        "description": job.company[:4096],
        "fields": [
            {"name": "Source", "value": job.source[:1024], "inline": True},
            {"name": "Posted", "value": (job.posted_date or "Unknown")[:1024], "inline": True},
        ],
    }


def _post_payload(payload: dict, webhook_url: str) -> None:
    response = requests.post(webhook_url, json=payload, timeout=20)
    if response.status_code != 429:
        response.raise_for_status()
        return

    retry_after = 1.0
    try:
        retry_after = float(response.json().get("retry_after", 1.0))
    except (TypeError, ValueError):
        pass

    LOGGER.warning("Discord rate limited; retrying in %.2f seconds", retry_after)
    time.sleep(retry_after)

    retry_response = requests.post(webhook_url, json=payload, timeout=20)
    retry_response.raise_for_status()


def send_batch(jobs: list[Job], webhook_url: str, batch_size: int = 10) -> None:
    if not jobs:
        return

    if not webhook_url:
        LOGGER.warning("Skipping Discord notify: missing DISCORD_WEBHOOK_URL")
        return

    batches = _chunk_jobs(jobs, batch_size)
    for index, batch in enumerate(batches):
        payload = {"embeds": [_build_embed(job) for job in batch]}
        _post_payload(payload, webhook_url)

        if index < len(batches) - 1:
            time.sleep(1.0)