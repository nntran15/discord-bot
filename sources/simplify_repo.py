from __future__ import annotations

import base64
import hashlib
import html
import logging
import re

import requests

from .base import Job


LOGGER = logging.getLogger(__name__)
README_API_URL = "https://api.github.com/repos/SimplifyJobs/New-Grad-Positions/contents/README.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    cells = [cell for cell in _split_row(line) if cell]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _strip_markdown(value: str) -> str:
    cleaned = MARKDOWN_LINK_PATTERN.sub(lambda match: match.group(1), value)
    cleaned = cleaned.replace("<br>", " ")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("`", "")
    return html.unescape(cleaned).strip()


def _extract_first_link(value: str) -> str:
    match = MARKDOWN_LINK_PATTERN.search(value)
    return match.group(2).strip() if match else ""


def _find_cell(headers: list[str], cells: list[str], keywords: tuple[str, ...]) -> str:
    for header, cell in zip(headers, cells):
        lowered = header.lower()
        if any(keyword in lowered for keyword in keywords):
            return cell
    return ""


def _row_to_job(headers: list[str], cells: list[str]) -> Job | None:
    company_cell = _find_cell(headers, cells, ("company",)) or (cells[0] if cells else "")
    title_cell = _find_cell(headers, cells, ("role", "title", "position"))
    if not title_cell and len(cells) > 1:
        title_cell = cells[1]

    url_cell = _find_cell(headers, cells, ("application", "apply", "link", "url"))
    posted_date_cell = _find_cell(headers, cells, ("date", "posted", "updated"))

    job_url = _extract_first_link(url_cell)
    if not job_url:
        for cell in cells:
            job_url = _extract_first_link(cell)
            if job_url:
                break

    company = _strip_markdown(company_cell)
    title = _strip_markdown(title_cell)
    posted_date = _strip_markdown(posted_date_cell)
    if not company or not title or not job_url:
        return None

    digest_input = f"{title}|{company}|{job_url}".encode("utf-8")
    digest = hashlib.sha256(digest_input).hexdigest()[:16]
    return Job(
        id=f"simplify:{digest}",
        title=title,
        company=company,
        url=job_url,
        source="simplify",
        posted_date=posted_date,
    )


def _parse_markdown_tables(markdown: str) -> list[Job]:
    jobs: list[Job] = []
    headers: list[str] = []
    lines = markdown.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            headers = []
            continue

        if index + 1 < len(lines) and _is_separator_row(lines[index + 1]):
            headers = [_strip_markdown(cell).lower() for cell in _split_row(line)]
            continue

        if not headers or _is_separator_row(line):
            continue

        cells = _split_row(line)
        if len(cells) != len(headers):
            continue

        job = _row_to_job(headers, cells)
        if job:
            jobs.append(job)

    return jobs


def fetch_jobs() -> list[Job]:
    try:
        response = requests.get(README_API_URL, timeout=20)
        response.raise_for_status()
        payload = response.json()
        encoded_content = payload.get("content", "")
        markdown = base64.b64decode(encoded_content).decode("utf-8")
    except Exception as exc:
        LOGGER.warning("Simplify repo fetch failed: %s", exc)
        return []

    return _parse_markdown_tables(markdown)