from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str
    company: str
    job_id: str
    title: str
    location: str
    url: str
    description: str = ""
    posted_at: datetime | None = None
    title_profile: str = "tech"
    location_label: str = ""
    min_years: int | None = None
    score: int | None = None
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.company}:{self.job_id}".lower()
