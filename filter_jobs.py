from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from sources.base import Job


MAX_JOB_AGE = timedelta(days=7)
US_STATE_CODES = {
    "AA",
    "AE",
    "AK",
    "AL",
    "AP",
    "AR",
    "AS",
    "AZ",
    "CA",
    "CO",
    "CT",
    "DC",
    "DE",
    "FL",
    "GA",
    "GU",
    "HI",
    "IA",
    "ID",
    "IL",
    "IN",
    "KS",
    "KY",
    "LA",
    "MA",
    "MD",
    "ME",
    "MI",
    "MN",
    "MO",
    "MP",
    "MS",
    "MT",
    "NC",
    "ND",
    "NE",
    "NH",
    "NJ",
    "NM",
    "NV",
    "NY",
    "OH",
    "OK",
    "OR",
    "PA",
    "PR",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UM",
    "UT",
    "VA",
    "VI",
    "VT",
    "WA",
    "WI",
    "WV",
    "WY",
}
US_LOCATION_KEYWORDS = (
    "united states",
    "united states of america",
    "usa",
    "u.s.a",
    "u.s.",
    "us-only",
    "us only",
    "remote us",
    "us remote",
)
FOREIGN_LOCATION_KEYWORDS = (
    "argentina",
    "australia",
    "austria",
    "belgium",
    "brazil",
    "canada",
    "china",
    "colombia",
    "costa rica",
    "czech",
    "denmark",
    "finland",
    "france",
    "germany",
    "hong kong",
    "india",
    "ireland",
    "israel",
    "italy",
    "japan",
    "london",
    "mexico",
    "netherlands",
    "new zealand",
    "norway",
    "philippines",
    "poland",
    "portugal",
    "romania",
    "singapore",
    "south africa",
    "spain",
    "sweden",
    "switzerland",
    "taiwan",
    "thailand",
    "toronto",
    "united kingdom",
    "uk",
    "vancouver",
    "vietnam",
)
WORKDAY_RELATIVE_PATTERN = re.compile(
    r"^posted\s+(?P<value>\d+)(?P<plus>\+?)\s+(?P<unit>minute|minutes|hour|hours|day|days|week|weeks)\s+ago$",
    re.IGNORECASE,
)
SHORT_RELATIVE_PATTERN = re.compile(r"^(?P<value>\d+)\s*(?P<unit>m|h|d|w)$", re.IGNORECASE)
STATE_CODE_PATTERN = re.compile(r",\s*(?P<state>[A-Z]{2})(?:\b|$)")


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
    now: datetime | None = None,
) -> list[Job]:
    include_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in include_patterns]
    exclude_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in exclude_patterns]
    current_time = now or datetime.now(timezone.utc)

    filtered: list[Job] = []
    for job in jobs:
        title = job.title or ""
        has_include = any(regex.search(title) for regex in include_regexes)
        has_exclude = any(regex.search(title) for regex in exclude_regexes)
        if has_include and not has_exclude and _is_us_job(job) and _was_posted_recently(job, current_time):
            filtered.append(job)

    return filtered


def _is_us_job(job: Job) -> bool:
    raw_location = getattr(job, "location", "") or ""
    if not raw_location.strip():
        return False

    location_parts = [
        part.strip()
        for part in re.split(r"(?:<br\s*/?>|</br>|\n|;|\|)", raw_location, flags=re.IGNORECASE)
        if part.strip()
    ]
    if not location_parts:
        return False

    return all(_is_us_location_part(part) for part in location_parts)


def _is_us_location_part(location: str) -> bool:
    normalized = re.sub(r"\s+", " ", location).strip().lower()
    if not normalized:
        return False

    if any(keyword in normalized for keyword in US_LOCATION_KEYWORDS):
        return True

    state_match = STATE_CODE_PATTERN.search(location.upper())
    if state_match and state_match.group("state") in US_STATE_CODES:
        return True

    if any(keyword in normalized for keyword in FOREIGN_LOCATION_KEYWORDS):
        return False

    return False


def _was_posted_recently(job: Job, now: datetime) -> bool:
    posted_date = (job.posted_date or "").strip()
    if not posted_date:
        return False

    exact_timestamp = _parse_iso_timestamp(posted_date)
    if exact_timestamp is not None:
        age = now - exact_timestamp
        return timedelta(0) <= age <= MAX_JOB_AGE

    normalized = posted_date.lower()
    if normalized in {"just now", "now", "posted just now"}:
        return True
    if normalized in {"today", "posted today", "0h", "0d", "yesterday", "posted yesterday"}:
        return True

    short_match = SHORT_RELATIVE_PATTERN.match(normalized)
    if short_match:
        value = int(short_match.group("value"))
        unit = short_match.group("unit").lower()
        unit_map = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
            "w": timedelta(weeks=value),
        }
        return unit_map[unit] <= MAX_JOB_AGE

    relative_match = WORKDAY_RELATIVE_PATTERN.match(posted_date)
    if relative_match:
        value = int(relative_match.group("value"))
        unit = relative_match.group("unit").lower()
        if unit.startswith("minute"):
            age = timedelta(minutes=value)
        elif unit.startswith("hour"):
            age = timedelta(hours=value)
        elif unit.startswith("day"):
            age = timedelta(days=value)
        else:
            age = timedelta(weeks=value)

        if relative_match.group("plus"):
            age += timedelta(seconds=1)

        return age <= MAX_JOB_AGE

    return False


def _parse_iso_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)