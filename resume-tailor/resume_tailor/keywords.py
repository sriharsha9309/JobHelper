import re
from collections import Counter

from .master import Master

_TECH_TERM = re.compile(r"\b(?:[A-Za-z]*[a-z][A-Z][A-Za-z0-9+#.-]*|[A-Z]{2,6}[0-9]*|[A-Za-z]+-?\d+[A-Za-z]*)\b")
_IGNORE_TERMS = {"AND", "OR", "THE", "USA", "US", "UK", "EU", "IT", "HR", "EEO", "CV", "JD", "FAQ", "OK", "ID", "NA", "TBD", "ETA"}


def phrase_regex(phrases: list[str]) -> re.Pattern:
    """Whole-phrase, case-insensitive match that also works for phrases like 'c#', '.net' or 'ci/cd'."""
    alternatives = "|".join(re.escape(p.lower()) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])", re.I)


def build_vocab(cfg_skills: dict, master: Master) -> dict[str, re.Pattern]:
    """Keyword -> regex: the config skill vocabulary plus every skill listed in the master resume."""
    vocab = {name: phrase_regex(aliases) for name, aliases in (cfg_skills or {}).items()}
    known = {k.lower() for k in vocab}
    for items in master.skills.values():
        for item in items:
            clean = re.sub(r"\s*\(.*?\)", "", item).strip()
            if clean and clean.lower() not in known:
                vocab[clean] = phrase_regex([clean])
                known.add(clean.lower())
    return vocab


def present(text: str, vocab: dict[str, re.Pattern]) -> set[str]:
    return {name for name, rx in vocab.items() if rx.search(text)}


def jd_keywords(jd: str, vocab: dict[str, re.Pattern]) -> Counter:
    return Counter({name: len(rx.findall(jd)) for name, rx in vocab.items() if rx.search(jd)})


def other_terms(jd: str, vocab: dict[str, re.Pattern], limit: int = 15) -> list[str]:
    """Tech-looking JD terms our vocabulary doesn't know (e.g. 'MLflow', 'GPT-4o') - review them manually."""
    counts = Counter(t for t in _TECH_TERM.findall(jd) if t.upper() not in _IGNORE_TERMS and len(t) > 1)
    return [t for t, _ in counts.most_common() if not present(t, vocab)][:limit]
