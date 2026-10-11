import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PLACEHOLDER = re.compile(r"<[^<>\n]{1,80}>")


@dataclass
class Bullet:
    id: str
    text: str
    tags: list[str] = field(default_factory=list)

    @property
    def is_placeholder(self) -> bool:
        return bool(PLACEHOLDER.search(self.text))


@dataclass
class Role:
    id: str
    company: str
    title: str
    location: str
    start: str
    end: str
    bullets: list[Bullet]
    min_bullets: int = 2
    max_bullets: int = 5


@dataclass
class Project:
    id: str
    name: str
    tech: list[str]
    link: str
    bullets: list[Bullet]
    max_bullets: int = 3


@dataclass
class Master:
    contact: dict
    headline: str
    years: str
    summary_points: list[str]
    skills: dict[str, list[str]]
    experience: list[Role]
    projects: list[Project]
    education: list[dict]
    certifications: list[str]

    def all_text(self) -> str:
        """Every fact except contact details (what the tailor and the AI may draw from)."""
        parts = [self.headline, self.years, *self.summary_points, *self.certifications]
        parts += [item for items in self.skills.values() for item in items]
        for r in self.experience:
            parts += [r.title, r.company, *(b.text for b in r.bullets), *(t for b in r.bullets for t in b.tags)]
        for p in self.projects:
            parts += [p.name, *p.tech, *(b.text for b in p.bullets), *(t for b in p.bullets for t in b.tags)]
        parts += [str(v) for e in self.education for v in e.values()]
        return "\n".join(parts)

    def placeholders(self) -> list[str]:
        text = self.all_text() + "\n" + "\n".join(str(v) for v in self.contact.values())
        return sorted(set(PLACEHOLDER.findall(text)))


def month_year(value) -> str:
    text = str(value or "").strip()
    if text.lower() in ("", "present", "current", "now"):
        return "Present"
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{_MONTHS[int(match.group(2)) - 1]} {match.group(1)}"
    return text


def _bullets(items, prefix: str) -> list[Bullet]:
    out = []
    for i, b in enumerate(items or [], 1):
        b = {"text": b} if isinstance(b, str) else b
        out.append(Bullet(id=str(b.get("id") or f"{prefix}-{i}"), text=str(b["text"]).strip(), tags=[str(t) for t in b.get("tags") or []]))
    return out


def parse_master(data: dict) -> Master:
    experience = [
        Role(
            id=str(r["id"]),
            company=str(r.get("company", "")),
            title=str(r.get("title", "")),
            location=str(r.get("location", "")),
            start=str(r.get("start", "")),
            end=str(r.get("end", "present")),
            bullets=_bullets(r.get("bullets"), str(r["id"])),
            min_bullets=int(r.get("min_bullets", 2)),
            max_bullets=int(r.get("max_bullets", 5)),
        )
        for r in data.get("experience") or []
    ]
    projects = [
        Project(
            id=str(p["id"]),
            name=str(p.get("name", "")),
            tech=[str(t) for t in p.get("tech") or []],
            link=str(p.get("link", "")),
            bullets=_bullets(p.get("bullets"), str(p["id"])),
            max_bullets=int(p.get("max_bullets", 3)),
        )
        for p in data.get("projects") or []
    ]
    master = Master(
        contact=dict(data.get("contact") or {}),
        headline=str(data.get("headline", "")),
        years=str(data.get("years", "")),
        summary_points=[str(s) for s in data.get("summary_points") or []],
        skills={str(g): [str(i) for i in items or []] for g, items in (data.get("skills") or {}).items()},
        experience=experience,
        projects=projects,
        education=[dict(e) for e in data.get("education") or []],
        certifications=[str(c) for c in data.get("certifications") or []],
    )
    ids = [b.id for r in experience for b in r.bullets] + [b.id for p in projects for b in p.bullets]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate bullet ids in master resume: {', '.join(sorted(duplicates))}")
    return master


def load_master(path: Path) -> Master:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - copy resume/master.example.yaml to resume/master.yaml and fill it in.")
    with open(path, encoding="utf-8") as f:
        return parse_master(yaml.safe_load(f) or {})
