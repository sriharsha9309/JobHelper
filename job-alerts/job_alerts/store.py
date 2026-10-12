import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job


class JobHistory:
    """Every matched job ever shown (key -> summary + first_seen). Used for de-duplication and jobs.html."""

    def __init__(self, path: Path, retention_days: int = 180):
        self.path = path
        self.retention = timedelta(days=retention_days)
        self.data: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def is_new(self, key: str) -> bool:
        return key not in self.data

    def add(self, job: Job) -> None:
        if job.key in self.data:
            return
        self.data[job.key] = {
            "key": job.key,
            "title": job.title,
            "company": job.company,
            "location_label": job.location_label,
            "url": job.url,
            "source": job.source,
            "min_years": job.min_years,
            "score": job.score,
            "matched_skills": job.matched_skills,
            "missing_skills": job.missing_skills,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }

    def recent(self, days: int) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [e for e in self.data.values() if datetime.fromisoformat(e["first_seen"]) >= cutoff]

    def save(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention
        self.data = {k: v for k, v in self.data.items() if datetime.fromisoformat(v["first_seen"]) >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
