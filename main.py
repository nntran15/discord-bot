from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from dedupe import dedupe_jobs, get_discovered_sources, init_db, is_seen, mark_seen
from filter_jobs import filter_jobs, load_filters
from notify_discord import send_batch
from sources import adzuna, ashby, greenhouse, lever, simplify_repo, workday
from sources.base import Job


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and notify on new junior SWE job postings.")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without notifying or writing state.")
    return parser.parse_args()


def load_companies(path: str = "config/companies.yaml") -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def print_dry_run(jobs: list[Job]) -> None:
    if not jobs:
        print("No new jobs would be sent.")
        return

    for job in jobs:
        print(f"[{job.source}] {job.company} | {job.title} | {job.url}")


def get_discovered_slugs(discovered_sources: list[dict], ats: str) -> list[str]:
    return sorted(
        {
            source["tenant"]
            for source in discovered_sources
            if source.get("ats") == ats and source.get("tenant")
        }
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    load_dotenv()
    conn = init_db()

    try:
        companies = load_companies()
        include_patterns, exclude_patterns = load_filters()
        discovered_sources = get_discovered_sources(conn)
        greenhouse_slugs = sorted(
            set(companies.get("greenhouse", [])) | set(get_discovered_slugs(discovered_sources, "greenhouse"))
        )
        lever_slugs = sorted(
            set(companies.get("lever", [])) | set(get_discovered_slugs(discovered_sources, "lever"))
        )
        ashby_slugs = sorted(
            set(companies.get("ashby", [])) | set(get_discovered_slugs(discovered_sources, "ashby"))
        )
        workday_sources = [source for source in discovered_sources if source.get("ats", "workday") == "workday"]

        fetched_jobs: list[Job] = []
        fetched_jobs.extend(greenhouse.fetch_all(greenhouse_slugs))
        fetched_jobs.extend(lever.fetch_all(lever_slugs))
        fetched_jobs.extend(ashby.fetch_all(ashby_slugs))
        fetched_jobs.extend(
            adzuna.fetch_jobs(
                app_id=os.getenv("ADZUNA_APP_ID", ""),
                app_key=os.getenv("ADZUNA_APP_KEY", ""),
            )
        )
        fetched_jobs.extend(simplify_repo.fetch_jobs())
        fetched_jobs.extend(workday.fetch_all(workday_sources))

        filtered_jobs = filter_jobs(fetched_jobs, include_patterns, exclude_patterns)
        unique_jobs = dedupe_jobs(filtered_jobs)
        new_jobs = [job for job in unique_jobs if not is_seen(conn, job)]
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        notified_count = 0

        if args.dry_run:
            print_dry_run(new_jobs)
        elif not new_jobs:
            pass
        elif not webhook_url:
            LOGGER.warning("Skipping Discord notify: missing DISCORD_WEBHOOK_URL")
        else:
            send_batch(new_jobs, webhook_url)
            for job in new_jobs:
                mark_seen(conn, job)
            notified_count = len(new_jobs)

        LOGGER.info(
            "Fetched %s jobs, %s passed filtering, %s were new, %s were notified.",
            len(fetched_jobs),
            len(unique_jobs),
            len(new_jobs),
            notified_count,
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())