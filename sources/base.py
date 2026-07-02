from dataclasses import dataclass


@dataclass
class Job:
    id: str
    title: str
    company: str
    url: str
    source: str
    posted_date: str = ""
    location: str = ""