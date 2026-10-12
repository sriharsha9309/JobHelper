from datetime import datetime, timedelta, timezone

import pytest

from job_alerts.config import load_config
from job_alerts.filters import Filters, min_years_required
from job_alerts.models import Job
from job_alerts.resume import find_skills, latex_to_text, load_resume_skills, score_job


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def filters(cfg):
    return Filters(cfg)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("We need 2-4 years of experience with Python.", 2),
        ("5+ years of experience overall. 2+ years experience with LLMs.", 5),
        ("Experience: 0 to 3 yrs in ML.", 0),
        ("Minimum 2.5 years of relevant experience.", 2),
        ("Founded 15 years ago. Great benefits.", None),
        ("", None),
    ],
)
def test_min_years_required(text, expected):
    assert min_years_required(text) == expected


@pytest.mark.parametrize(
    "title, ok",
    [
        ("GenAI Engineer", True),
        ("AI Engineer - LLM Applications", True),
        ("Machine Learning Engineer II", True),
        ("Senior ML Engineer", False),
        ("Sr. AI Engineer", False),
        ("Staff Applied Scientist", False),
        ("AI Sales Manager", False),
        ("Retail Associate", False),
        ("Email Marketing Specialist", False),
    ],
)
def test_title_filter(filters, title, ok):
    assert filters.title_ok(title) is ok


@pytest.mark.parametrize(
    "location, label",
    [
        ("Bangalore, Karnataka, India", "Bengaluru"),
        ("Gurgaon, Haryana", "Delhi NCR"),
        ("Copenhagen, Denmark", "Denmark"),
        ("Remote - India", "Remote (India/APAC)"),
        ("Remote - US", None),
        ("India", "India (city not stated)"),
        ("San Francisco, CA", None),
    ],
)
def test_location_label(filters, location, label):
    assert filters.location_label(location) == label


def _job(**overrides):
    base = dict(
        source="test", company="acme", job_id="1", title="AI Engineer", location="Hyderabad, India",
        url="https://example.com/1", description="1-3 years of experience with LangGraph and AWS.",
        posted_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return Job(**base)


def test_accept_annotates_job(filters):
    job = _job()
    assert filters.accept(job)
    assert job.location_label == "Hyderabad"
    assert job.min_years == 1


def test_accept_rejects_senior_experience(filters):
    assert not filters.accept(_job(description="Requires 6+ years of experience."))


def test_accept_rejects_stale_posting(filters):
    assert not filters.accept(_job(posted_at=datetime.now(timezone.utc) - timedelta(days=90)))


def test_latex_to_text_strips_commands():
    text = latex_to_text(r"\section{Skills} \textbf{LangGraph}, Python % comment AWS")
    assert "langgraph" in text and "python" in text and "aws" not in text


def test_score_job(cfg):
    _, vocab = load_resume_skills({"skills": cfg["skills"], "resume_path": "does/not/exist.tex"})
    resume_skills = find_skills("python langgraph aws rag", vocab)
    job = _job(description="Python, LangGraph, Kubernetes and RAG experience.")
    score_job(job, resume_skills, vocab)
    assert job.score == 75
    assert job.missing_skills == ["kubernetes"]
