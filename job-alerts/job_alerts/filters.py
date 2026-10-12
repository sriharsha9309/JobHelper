import re
from datetime import datetime, timedelta, timezone

from .models import Job

# "2 years", "3+ yrs", "1-3 years", "2 to 4 years", "2.5 years"
_YEARS_RE = re.compile(
    r"(?<![\d.])(\d{1,2})(?:\.\d+)?\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*\d{1,2}(?:\.\d+)?\s*\+?\s*)?(?:years?|yrs?)\b",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.;!?•])\s+|\s+[-*•]\s+")
_EXPERIENCE_WORD = re.compile(r"experience|\bexp\b", re.I)


def phrase_regex(phrases: list[str]) -> re.Pattern:
    """Whole-phrase, case-insensitive match that also works for phrases ending in punctuation (e.g. 'sr.')."""
    alternatives = "|".join(re.escape(p.lower()) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])", re.I)


def min_years_required(text: str) -> int | None:
    """Highest lower bound of years mentioned in experience sentences, so '5+ years overall, 2+ with LLMs' -> 5."""
    floors = []
    for sentence in _SENTENCE_SPLIT.split(text or ""):
        if not _EXPERIENCE_WORD.search(sentence):
            continue
        floors.extend(int(m.group(1)) for m in _YEARS_RE.finditer(sentence) if int(m.group(1)) <= 20)
    return max(floors) if floors else None


class Filters:
    def __init__(self, cfg: dict):
        self.include = phrase_regex(cfg["title"]["include"])
        self.exclude = phrase_regex(cfg["title"]["exclude"])
        self.allow = {
            name: phrase_regex(profile["allow"])
            for name, profile in (cfg["title"].get("profiles") or {}).items()
            if profile and profile.get("allow")
        }
        self.max_years = cfg["experience"]["max_years"]
        self.keep_unknown = cfg["experience"].get("keep_when_not_stated", True)
        loc = cfg["locations"]
        self.cities = {label: phrase_regex(words) for label, words in loc["include"].items()}
        self.remote = phrase_regex(loc["remote_words"])
        self.remote_regions = phrase_regex(loc["remote_requires_any"])
        self.country_only = {label: phrase_regex(words) for label, words in (loc.get("country_only") or {}).items()}
        self.max_age = timedelta(days=cfg.get("max_age_days", 30))

    def title_ok(self, title: str, profile: str = "tech") -> bool:
        """Profile 'allow' phrases (e.g. 'assistant vice president' for banks) are removed before the exclude check."""
        if not self.include.search(title):
            return False
        allow = self.allow.get(profile)
        cleaned = allow.sub(" ", title) if allow else title
        return not self.exclude.search(cleaned)

    def location_label(self, location: str) -> str | None:
        for label, rx in self.cities.items():
            if rx.search(location):
                return label
        if self.remote.search(location) and self.remote_regions.search(location):
            return "Remote (India/APAC)"
        for label, rx in self.country_only.items():
            if rx.search(location):
                return label
        return None

    def accept(self, job: Job) -> bool:
        """Apply all filters; on success, annotate the job with location label and required years."""
        if not self.title_ok(job.title, job.title_profile):
            return False
        label = self.location_label(job.location)
        if not label:
            return False
        if job.posted_at and datetime.now(timezone.utc) - job.posted_at > self.max_age:
            return False
        years = min_years_required(job.description)
        if years is None and not self.keep_unknown:
            return False
        if years is not None and years > self.max_years:
            return False
        job.location_label = label
        job.min_years = years
        return True
