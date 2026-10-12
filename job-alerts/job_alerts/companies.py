import csv
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

AUTO_ATS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workday")
FIELDS = ["company", "category", "priority", "location_focus", "title_profile", "ats", "ats_id", "careers_url", "notes"]
# companies.html uses the same start date and formula for its "due today" list.
ROTATION_START = date(2026, 10, 1)

_AUTO_PATTERNS = [
    ("workday", re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"(?:job-)?boards\.greenhouse\.io/(?!embed\b)([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)")),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
]
_MANUAL_SIGNS = {
    "successfactors": "SuccessFactors",
    "taleo.net": "Taleo",
    "oraclecloud.com": "Oracle HCM",
    "eightfold.ai": "Eightfold",
    "phenompeople": "Phenom",
    "darwinbox": "Darwinbox",
    "avature": "Avature",
    "icims.com": "iCIMS",
    "keka.com": "Keka",
    "brassring": "BrassRing",
    "workable.com": "Workable",
}


@dataclass
class Company:
    company: str
    category: str
    priority: str
    location_focus: str
    title_profile: str
    ats: str
    ats_id: str
    careers_url: str
    notes: str

    @property
    def is_auto(self) -> bool:
        return self.ats in AUTO_ATS and bool(self.ats_id)

    @property
    def platform(self) -> str:
        match = re.search(r"platform:\s*([^;]+)", self.notes)
        return match.group(1).strip() if match else ""

    def set_platform(self, platform: str) -> None:
        parts = [p for p in self.notes.split(";") if p.strip() and not p.strip().startswith("platform:")]
        if platform:
            parts.append(f"platform: {platform}")
        self.notes = "; ".join(p.strip() for p in parts)

    def links(self) -> dict[str, str]:
        loc = self.location_focus or "India"
        out = {}
        if self.careers_url.startswith(("https://", "http://")):
            out["Careers"] = self.careers_url
        out["LinkedIn"] = (
            "https://www.linkedin.com/jobs/search/?keywords="
            f"{quote_plus(self.company + ' AI')}&location={quote_plus(loc)}&f_TPR=r604800"
        )
        out["Google"] = "https://www.google.com/search?q=" + quote_plus(f"{self.company} careers AI ML engineer {loc}")
        return out


def load_companies(path: Path) -> list[Company]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [Company(**{k: (r.get(k) or "").strip() for k in FIELDS}) for r in rows if (r.get("company") or "").strip()]


def save_companies(path: Path, companies: list[Company]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(asdict(c) for c in companies)
    tmp.replace(path)


def due_today(companies: list[Company], rotation_days: dict, today: date | None = None) -> list[Company]:
    """Manual companies spread over their priority period, each due on a fixed day of the cycle."""
    day = ((today or date.today()) - ROTATION_START).days
    due = []
    for c in companies:
        if c.is_auto:
            continue
        period = int(rotation_days.get(c.priority, 14))
        if day % period == sum(map(ord, c.company)) % period:
            due.append(c)
    return sorted(due, key=lambda c: (c.priority, c.category, c.company))


def detect_platform(final_url: str, page_text: str) -> tuple[str, str, str]:
    """Return (ats, ats_id, platform_name) from a careers page URL + HTML."""
    haystack = f"{final_url}\n{page_text}"
    for ats, rx in _AUTO_PATTERNS:
        match = rx.search(haystack)
        if match:
            ats_id = "|".join(match.groups()) if ats == "workday" else match.group(1)
            return ats, ats_id, ""
    lowered = haystack.lower()
    for sign, name in _MANUAL_SIGNS.items():
        if sign in lowered:
            return "manual", "", name
    return "manual", "", "unknown"
