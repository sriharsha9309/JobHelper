import logging
import re

from .config import ROOT
from .filters import phrase_regex
from .models import Job

log = logging.getLogger(__name__)


def latex_to_text(src: str) -> str:
    src = re.sub(r"(?<!\\)%.*", " ", src)
    src = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", src)
    src = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", src)
    src = src.replace("{", " ").replace("}", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", src).lower()


def find_skills(text: str, vocab: dict[str, re.Pattern]) -> set[str]:
    return {name for name, rx in vocab.items() if rx.search(text)}


def load_resume_skills(cfg: dict) -> tuple[set[str] | None, dict[str, re.Pattern]]:
    vocab = {name: phrase_regex(aliases) for name, aliases in (cfg.get("skills") or {}).items()}
    path = ROOT / cfg.get("resume_path", "resume/resume.tex")
    if not path.exists():
        log.info("No resume at %s - match scores disabled", path)
        return None, vocab
    skills = find_skills(latex_to_text(path.read_text(encoding="utf-8")), vocab)
    log.info("Resume skills detected (%d): %s", len(skills), ", ".join(sorted(skills)))
    return skills, vocab


def score_job(job: Job, resume_skills: set[str] | None, vocab: dict[str, re.Pattern]) -> None:
    """Score = share of the job's recognised skills that appear in the resume."""
    if resume_skills is None:
        return
    job_skills = find_skills(f"{job.title} {job.description}", vocab)
    if not job_skills:
        return
    matched = job_skills & resume_skills
    job.score = round(100 * len(matched) / len(job_skills))
    job.matched_skills = sorted(matched)
    job.missing_skills = sorted(job_skills - resume_skills)
