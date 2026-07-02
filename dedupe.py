from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sources.base import Job


SEEN_JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    id TEXT PRIMARY KEY,
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
    _ensure_discovered_sources_schema(conn)
    conn.commit()
    return conn


def is_seen(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, job: Job) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO seen_jobs (id, title, company, url, source, posted_date, notified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.id,
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