from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sources.base import Job


SEEN_JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_date TEXT,
    notified_at TEXT NOT NULL
);
"""


DISCOVERED_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovered_sources (
    tenant TEXT NOT NULL,
    pod TEXT NOT NULL,
    site TEXT NOT NULL,
    ats TEXT NOT NULL DEFAULT 'workday',
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (ats, tenant, pod, site)
);
"""


EXPECTED_DISCOVERED_SOURCE_PK = ["ats", "tenant", "pod", "site"]
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"ref", "fbclid", "gclid", "mc_cid", "mc_eid"}
SOURCE_PRIORITY = {
    "greenhouse": 0,
    "lever": 0,
    "workday": 0,
    "custom": 0,
    "adzuna": 1,
    "simplify": 2,
}


def _ensure_seen_jobs_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(seen_jobs)").fetchall()
    if not rows:
        conn.execute(SEEN_JOBS_SCHEMA)
        return

    column_names = [row[1] for row in rows]
    if "dedupe_key" in column_names:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_seen_jobs_dedupe_key ON seen_jobs(dedupe_key)")
        return

    conn.execute(
        """
        CREATE TABLE seen_jobs_new (
            id TEXT PRIMARY KEY,
            dedupe_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            posted_date TEXT,
            notified_at TEXT NOT NULL
        )
        """
    )

    existing_rows = conn.execute(
        "SELECT id, title, company, url, source, posted_date, notified_at FROM seen_jobs"
    ).fetchall()
    for row in existing_rows:
        job = Job(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            url=row["url"],
            source=row["source"],
            posted_date=row["posted_date"] or "",
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO seen_jobs_new (id, dedupe_key, title, company, url, source, posted_date, notified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job_dedupe_key(job),
                job.title,
                job.company,
                job.url,
                job.source,
                job.posted_date,
                row["notified_at"],
            ),
        )

    conn.execute("DROP TABLE seen_jobs")
    conn.execute("ALTER TABLE seen_jobs_new RENAME TO seen_jobs")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlsplit(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    normalized_query = urlencode(sorted(query_pairs))
    normalized_path = parsed.path.rstrip("/") or "/"
    normalized_netloc = parsed.netloc.lower()
    if normalized_netloc.startswith("www."):
        normalized_netloc = normalized_netloc[4:]

    return urlunsplit(
        (
            parsed.scheme.lower(),
            normalized_netloc,
            normalized_path,
            normalized_query,
            "",
        )
    )


def job_dedupe_key(job: Job) -> str:
    normalized_url = _normalize_url(job.url)
    if normalized_url:
        return f"url:{normalized_url}"

    location = _normalize_text(job.location)
    return f"role:{_normalize_text(job.company)}|{_normalize_text(job.title)}|{location}"


def _job_priority(job: Job) -> int:
    return SOURCE_PRIORITY.get(job.source, 99)


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    kept_by_key: dict[str, Job] = {}
    ordered_keys: list[str] = []

    for job in jobs:
        dedupe_key = job_dedupe_key(job)
        existing = kept_by_key.get(dedupe_key)
        if existing is None:
            kept_by_key[dedupe_key] = job
            ordered_keys.append(dedupe_key)
            continue

        if _job_priority(job) < _job_priority(existing):
            kept_by_key[dedupe_key] = job

    return [kept_by_key[dedupe_key] for dedupe_key in ordered_keys]


def _ensure_discovered_sources_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(discovered_sources)").fetchall()
    if not rows:
        conn.execute(DISCOVERED_SOURCES_SCHEMA)
        return

    primary_key_columns = [row[1] for row in sorted(rows, key=lambda row: row[5]) if row[5] > 0]
    if primary_key_columns == EXPECTED_DISCOVERED_SOURCE_PK:
        return

    conn.execute(
        """
        CREATE TABLE discovered_sources_new (
            tenant TEXT NOT NULL,
            pod TEXT NOT NULL,
            site TEXT NOT NULL,
            ats TEXT NOT NULL DEFAULT 'workday',
            discovered_at TEXT NOT NULL,
            PRIMARY KEY (ats, tenant, pod, site)
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO discovered_sources_new (tenant, pod, site, ats, discovered_at)
        SELECT tenant, pod, site, COALESCE(ats, 'workday'), discovered_at
        FROM discovered_sources
        """
    )
    conn.execute("DROP TABLE discovered_sources")
    conn.execute("ALTER TABLE discovered_sources_new RENAME TO discovered_sources")


def init_db(path: str = "db/jobs.sqlite") -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SEEN_JOBS_SCHEMA)
    conn.execute(DISCOVERED_SOURCES_SCHEMA)
    _ensure_seen_jobs_schema(conn)
    _ensure_discovered_sources_schema(conn)
    conn.commit()
    return conn


def is_seen(conn: sqlite3.Connection, job_or_id: Job | str) -> bool:
    if isinstance(job_or_id, Job):
        row = conn.execute(
            "SELECT 1 FROM seen_jobs WHERE id = ? OR dedupe_key = ? LIMIT 1",
            (job_or_id.id, job_dedupe_key(job_or_id)),
        ).fetchone()
        return row is not None

    row = conn.execute("SELECT 1 FROM seen_jobs WHERE id = ? LIMIT 1", (job_or_id,)).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, job: Job) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO seen_jobs (id, dedupe_key, title, company, url, source, posted_date, notified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.id,
            job_dedupe_key(job),
            job.title,
            job.company,
            job.url,
            job.source,
            job.posted_date,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def get_discovered_sources(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT tenant, pod, site, ats, discovered_at FROM discovered_sources ORDER BY discovered_at"
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_discovered_source(
    conn: sqlite3.Connection,
    tenant: str,
    pod: str,
    site: str,
    ats: str = "workday",
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO discovered_sources (tenant, pod, site, ats, discovered_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tenant, pod, site, ats, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cursor.rowcount > 0