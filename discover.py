from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from dedupe import init_db, upsert_discovered_source
from discovery import run_discovery


LOGGER = logging.getLogger(__name__)


def load_queries(path: str = "config/discovery_queries.yaml") -> list[str]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("queries", []))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    conn = init_db()

    try:
        brave_api_key = os.getenv("BRAVE_API_KEY", "")
        if not brave_api_key:
            LOGGER.warning("Skipping source discovery: missing BRAVE_API_KEY")
            return 0

        queries = load_queries()
        discovered_sources = run_discovery(
            queries=queries,
            api_key=brave_api_key,
        )

        inserted_count = 0
        for source in discovered_sources:
            if upsert_discovered_source(
                conn,
                tenant=source["tenant"],
                pod=source["pod"],
                site=source["site"],
                ats=source["ats"],
            ):
                inserted_count += 1

        LOGGER.info("Found %s new discovered sources.", inserted_count)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())