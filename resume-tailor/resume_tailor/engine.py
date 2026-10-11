import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field

from .gemini import GeminiError, generate_json
from .keywords import build_vocab, jd_keywords, other_terms, present
from .master import Bullet, Master, Project, Role

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|lead|principal|staff|manager|head|director|architect)\b", re.I)


@dataclass
class TailoredResume:
    contact: dict
    headline: str
    summary: list[str]
    skills: dict[str, list[str]]
    experience: list[tuple[Role, list[str]]]
    projects: list[tuple[Project, list[str]]]
    education: list[dict]
    certifications: list[str]


@dataclass
class TailorResult:
    resume: TailoredResume
    mode: str
    jd_keywords: list[str]
    matched: list[str]
    not_shown: list[str]
    not_in_master: list[str]
    other_terms: list[str]
    keyword_count: int
    coverage_before: int
    coverage_after: int
    warnings: list[str] = field(default_factory=list)


# ---------- scoring & keyword-only tailoring ----------

def _score(text: str, jdk: Counter, vocab) -> float:
    return sum(1 + 0.5 * min(jdk[k], 3) for k in present(text, vocab) & jdk.keys())


def _bullet_score(b: Bullet, jdk: Counter, vocab) -> float:
    return _score(f"{b.text} {' '.join(b.tags)}", jdk, vocab) + (0.3 if _NUMBER.search(b.text) else 0)


def _ranked(bullets: list[Bullet], jdk: Counter, vocab) -> list[Bullet]:
    return sorted((b for b in bullets if not b.is_placeholder), key=lambda b: -_bullet_score(b, jdk, vocab))


def _pick(ranked: list[Bullet], jdk: Counter, vocab, lo: int, hi: int) -> list[Bullet]:
    relevant = sum(1 for b in ranked if _bullet_score(b, jdk, vocab) >= 1)
    return ranked[: min(len(ranked), max(lo, min(hi, relevant)))]


def _order_skills(skills: dict[str, list[str]], priority: list[str]) -> dict[str, list[str]]:
    rank = {s.lower(): i for i, s in enumerate(priority)}
    last = len(rank) + 1
    groups = {g: sorted(items, key=lambda s: rank.get(s.lower(), last)) for g, items in skills.items() if items}
    return dict(sorted(groups.items(), key=lambda kv: min(rank.get(s.lower(), last) for s in kv[1])))


def _keyword_priority(master: Master, jdk: Counter, vocab) -> list[str]:
    items = [i for items in master.skills.values() for i in items]
    scored = [(i, _score(i, jdk, vocab)) for i in items]
    return [i for i, s in sorted(scored, key=lambda x: -x[1]) if s > 0]


def _trim_to_budget(selection: dict[str, list[Bullet]], roles: list[Role], budget: int) -> None:
    while sum(len(v) for v in selection.values()) > budget:
        trimmable = [r for r in roles if len(selection[r.id]) > r.min_bullets]
        if not trimmable:
            return
        selection[max(trimmable, key=lambda r: len(selection[r.id])).id].pop()


def keyword_tailor(master: Master, jdk: Counter, vocab, headline: str, settings: dict):
    """Pick and order true content by JD keyword overlap. Returns (resume, bullet selection by owner id)."""
    selection: dict[str, list[Bullet]] = {
        r.id: _pick(_ranked(r.bullets, jdk, vocab), jdk, vocab, r.min_bullets, r.max_bullets) for r in master.experience
    }
    _trim_to_budget(selection, master.experience, int(settings.get("max_total_bullets", 14)))

    project_scores = []
    for p in master.projects:
        ranked = _ranked(p.bullets, jdk, vocab)
        if ranked:
            project_scores.append((p, ranked, max(_bullet_score(b, jdk, vocab) for b in ranked)))
    project_scores.sort(key=lambda x: -x[2])
    for p, ranked, _ in project_scores[: int(settings.get("max_projects", 2))]:
        selection[p.id] = _pick(ranked, jdk, vocab, 1, p.max_bullets)

    points = sorted((s for s in master.summary_points if "<" not in s), key=lambda s: -_score(s, jdk, vocab))
    summary = [f"{headline} with {master.years} years of experience."] + points[:3]

    resume = TailoredResume(
        contact=master.contact,
        headline=headline,
        summary=summary,
        skills=_order_skills(master.skills, _keyword_priority(master, jdk, vocab)),
        experience=[(r, [b.text for b in selection[r.id]]) for r in master.experience],
        projects=[(p, [b.text for b in selection[p.id]]) for p in master.projects if p.id in selection],
        education=master.education,
        certifications=[c for c in master.certifications if "<" not in c],
    )
    return resume, selection


# ---------- AI tailoring with guardrails ----------

_SYSTEM = """You tailor a candidate's resume to one job description so it surfaces in ATS keyword searches.
Rules:
- Use ONLY facts in MASTER. Never invent employers, titles, dates, numbers, metrics, tools or skills.
- You may rephrase a bullet to use the job description's exact terms ONLY when that bullet's text or tags support the term.
- Each bullet: one sentence, starts with a strong past-tense action verb, at most 30 words, no first person.
- For every role choose the most relevant bullets (best first) within that role's min/max, using the given bullet ids.
- For projects choose at most the given max bullets.
- Summary: 2-4 short sentences grounded in MASTER that naturally use the job's key terms. No keyword stuffing.
- skills_priority: skills from MASTER only, most relevant to the job first."""

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "ARRAY", "items": {"type": "STRING"}},
        "bullets": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"source_id": {"type": "STRING"}, "text": {"type": "STRING"}},
                "required": ["source_id", "text"],
            },
        },
        "skills_priority": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["summary", "bullets", "skills_priority"],
}


def check_rewrite(new_text: str, source_text: str, vocab) -> str | None:
    """Reason the rewrite is unsafe, or None. Blocks invented numbers and skills not in the source."""
    if not new_text or len(new_text) > 350:
        return "empty or too long"
    source_numbers = set(_NUMBER.findall(source_text))
    invented = [n for n in _NUMBER.findall(new_text) if n not in source_numbers]
    if invented:
        return f"introduced numbers not in the original ({', '.join(invented)})"
    added = present(new_text, vocab) - present(source_text, vocab)
    if added:
        return f"added skills the original does not support ({', '.join(sorted(added))})"
    return None


def _ai_prompt(master: Master, jd: str, title: str, company: str) -> str:
    def bullets(items):
        return [{"id": b.id, "text": b.text, "tags": b.tags} for b in items if not b.is_placeholder]

    facts = {
        "summary_points": [s for s in master.summary_points if "<" not in s],
        "years_of_experience": master.years,
        "skills": master.skills,
        "certifications": [c for c in master.certifications if "<" not in c],
        "roles": [
            {"id": r.id, "title": r.title, "company": r.company, "min": r.min_bullets, "max": r.max_bullets, "bullets": bullets(r.bullets)}
            for r in master.experience
        ],
        "projects": [{"id": p.id, "name": p.name, "tech": p.tech, "max": p.max_bullets, "bullets": bullets(p.bullets)} for p in master.projects],
    }
    return json.dumps({"job_title": title, "company": company, "job_description": jd[:12000], "MASTER": facts}, ensure_ascii=False)


def apply_ai(master: Master, base: TailoredResume, selection: dict[str, list[Bullet]], data: dict, vocab, settings: dict, warnings: list[str]) -> TailoredResume:
    owners: dict[str, tuple[str, Bullet]] = {}
    for r in master.experience:
        owners.update({b.id: (r.id, b) for b in r.bullets})
    for p in master.projects:
        owners.update({b.id: (p.id, b) for b in p.bullets})

    chosen: dict[str, list[tuple[str, str]]] = {}
    for item in data.get("bullets") or []:
        sid = str(item.get("source_id", "")).strip()
        if sid not in owners:
            warnings.append(f"AI referenced unknown bullet '{sid}' - ignored")
            continue
        owner, src = owners[sid]
        if src.is_placeholder or any(sid == s for s, _ in chosen.get(owner, [])):
            continue
        text = " ".join(str(item.get("text", "")).split())
        problem = check_rewrite(text, f"{src.text} {' '.join(src.tags)}", vocab)
        if problem:
            warnings.append(f"Kept original wording for '{sid}': AI {problem}")
            text = src.text
        chosen.setdefault(owner, []).append((sid, text))

    def finalize(owner_id: str, lo: int, hi: int) -> list[str]:
        picked = chosen.get(owner_id, [])[:hi]
        used = {sid for sid, _ in picked}
        for b in selection.get(owner_id, []):
            if len(picked) >= lo:
                break
            if b.id not in used:
                picked.append((b.id, b.text))
        return [text for _, text in picked]

    experience = [(r, finalize(r.id, r.min_bullets, r.max_bullets)) for r in master.experience]
    budget = int(settings.get("max_total_bullets", 14))
    while sum(len(b) for _, b in experience) > budget:
        trimmable = [(i, r) for i, (r, b) in enumerate(experience) if len(b) > r.min_bullets]
        if not trimmable:
            break
        i, _ = max(trimmable, key=lambda x: len(experience[x[0]][1]))
        experience[i][1].pop()

    projects = [(p, finalize(p.id, 1, p.max_bullets)) for p, _ in base.projects]

    master_text = master.all_text()
    summary = []
    for sentence in (data.get("summary") or [])[:4]:
        sentence = " ".join(str(sentence).split())
        problem = check_rewrite(sentence, master_text, vocab)
        if problem:
            warnings.append(f"Dropped an AI summary sentence: {problem}")
        else:
            summary.append(sentence)
    if len(summary) < 2:
        summary = base.summary

    known = {i.lower(): i for items in master.skills.values() for i in items}
    priority = [known[s.lower()] for s in data.get("skills_priority") or [] if isinstance(s, str) and s.lower() in known]
    priority += [s for s in base_priority(base) if s not in priority]

    return TailoredResume(
        contact=base.contact,
        headline=base.headline,
        summary=summary,
        skills=_order_skills(master.skills, priority),
        experience=experience,
        projects=projects,
        education=base.education,
        certifications=base.certifications,
    )


def base_priority(resume: TailoredResume) -> list[str]:
    return [i for items in resume.skills.values() for i in items]


# ---------- public entry point ----------

def resume_text(r: TailoredResume) -> str:
    parts = [r.headline, *r.summary, *(i for items in r.skills.values() for i in items), *r.certifications]
    parts += [f"{role.title} {role.company} {' '.join(b)}" for role, b in r.experience]
    parts += [f"{p.name} {' '.join(p.tech)} {' '.join(b)}" for p, b in r.projects]
    return "\n".join(parts)


def _default_text(master: Master) -> str:
    """The untailored resume: master headline, summary and the first bullets of each role."""
    parts = [master.headline, *master.summary_points, *(i for items in master.skills.values() for i in items)]
    for r in master.experience:
        parts += [b.text for b in r.bullets if not b.is_placeholder][: r.max_bullets]
    return "\n".join(parts)


def tailor(master: Master, jd: str, title: str, company: str, cfg: dict, use_exact_title: bool = True, use_ai: bool = True) -> TailorResult:
    settings = cfg.get("tailor") or {}
    vocab = build_vocab(cfg.get("skills") or {}, master)
    jdk = jd_keywords(jd, vocab)
    warnings: list[str] = []

    title = " ".join((title or "").split())
    headline = title if use_exact_title and title else master.headline
    if use_exact_title and title and _SENIOR_TITLE.search(title):
        warnings.append(f"The JD title '{title}' looks senior - make sure you genuinely fit it before using it as your headline.")

    resume, selection = keyword_tailor(master, jdk, vocab, headline, settings)
    mode = "keywords"
    api_key = os.getenv("GEMINI_API_KEY")
    if use_ai and api_key:
        try:
            data = generate_json(api_key, settings.get("model", "gemini-2.5-flash"), _SYSTEM, _ai_prompt(master, jd, title, company), _SCHEMA)
            resume = apply_ai(master, resume, selection, data, vocab, settings, warnings)
            mode = "ai"
        except GeminiError as exc:
            warnings.append(f"Gemini unavailable ({exc}) - used keyword-only tailoring.")
    elif use_ai:
        warnings.append("GEMINI_API_KEY not set in .env - used keyword-only tailoring.")

    keys = set(jdk)
    after = present(resume_text(resume), vocab) & keys
    before = present(_default_text(master), vocab) & keys
    in_master = present(master.all_text(), vocab)
    keyword_count = len(present(resume_text(resume), vocab))
    lo, hi = settings.get("keyword_target", [25, 35])
    if keyword_count < lo:
        warnings.append(f"{keyword_count} role keywords on the resume (target {lo}-{hi}). Add TRUE skills or bullet tags to master.yaml if you have them.")
    elif keyword_count > hi:
        warnings.append(f"{keyword_count} role keywords (target {lo}-{hi}) - consider trimming the skills list to avoid looking stuffed.")

    placeholders = master.placeholders()
    if placeholders:
        warnings.insert(0, f"master.yaml still has {len(placeholders)} placeholder(s) such as {placeholders[0]} - fill them before applying.")

    def pct(found):
        return round(100 * len(found) / len(keys)) if keys else 0

    ranked_keys = [k for k, _ in jdk.most_common()]
    return TailorResult(
        resume=resume,
        mode=mode,
        jd_keywords=ranked_keys,
        matched=[k for k in ranked_keys if k in after],
        not_shown=[k for k in ranked_keys if k not in after and k in in_master],
        not_in_master=[k for k in ranked_keys if k not in in_master],
        other_terms=other_terms(jd, vocab),
        keyword_count=keyword_count,
        coverage_before=pct(before),
        coverage_after=pct(after),
        warnings=warnings,
    )
