from __future__ import annotations

import re
from pathlib import Path

import yaml

from sources.base import Job


def load_filters(path: str = "config/filters.yaml") -> tuple[list[str], list[str]]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    include_patterns = list(data.get("include_patterns", []))
    exclude_patterns = list(data.get("exclude_patterns", []))
    return include_patterns, exclude_patterns


def filter_jobs(
    jobs: list[Job],
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[Job]:
    include_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in include_patterns]
    exclude_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in exclude_patterns]

    filtered: list[Job] = []
    for job in jobs:
        title = job.title or ""
        has_include = any(regex.search(title) for regex in include_regexes)
        has_exclude = any(regex.search(title) for regex in exclude_regexes)
        if has_include and not has_exclude:
            filtered.append(job)

    return filtered