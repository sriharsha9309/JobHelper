from collections import Counter
from datetime import date, timedelta

import pytest

from job_alerts.companies import AUTO_ATS, Company, detect_platform, due_today, load_companies
from job_alerts.config import ROOT, load_config
from job_alerts.filters import Filters
from job_alerts.page import build_page
from job_alerts.sources import _workday_posted


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def companies(cfg):
    return load_companies(ROOT / cfg["companies_csv"])


def test_csv_is_well_formed(cfg, companies):
    assert len(companies) > 150
    names = Counter(c.company for c in companies)
    assert not [n for n, k in names.items() if k > 1], "duplicate company names"
    profiles = set(cfg["title"]["profiles"])
    for c in companies:
        assert c.priority in cfg["rotation_days"], c.company
        assert c.title_profile in profiles, c.company
        assert c.ats in ("", "manual", *AUTO_ATS), c.company
        assert not c.careers_url or c.careers_url.startswith("https://"), c.company


def test_each_manual_company_is_due_once_per_period(cfg, companies):
    rotation = cfg["rotation_days"]
    start = date(2026, 10, 1)
    for priority, period in rotation.items():
        group = [c for c in companies if c.priority == priority and not c.is_auto]
        hits = Counter(c.company for d in range(period) for c in due_today(group, rotation, start + timedelta(days=d)))
        assert all(hits[c.company] == 1 for c in group)


@pytest.mark.parametrize(
    "title, profile, ok",
    [
        ("Assistant Vice President - GenAI", "bank", True),
        ("Deputy Manager - Data Science", "bank", True),
        ("Vice President - AI", "bank", False),
        ("Senior Manager - AI", "bank", False),
        ("Senior Data Scientist", "consulting", True),
        ("Senior Manager - AI", "consulting", False),
        ("Senior Data Scientist", "tech", False),
        ("Assistant Vice President - GenAI", "tech", False),
    ],
)
def test_title_profiles(cfg, title, profile, ok):
    assert Filters(cfg).title_ok(title, profile) is ok


@pytest.mark.parametrize(
    "url, html, expected",
    [
        ("https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal", "", ("workday", "walmart|wd5|WalmartExternal", "")),
        ("https://acme.com/careers", '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>', ("greenhouse", "acme", "")),
        ("https://acme.com/careers", '<a href="https://jobs.lever.co/acme-ai/123">', ("lever", "acme-ai", "")),
        ("https://career5.successfactors.eu/careers?company=x", "", ("manual", "", "SuccessFactors")),
        ("https://acme.com/careers", "<html>custom</html>", ("manual", "", "unknown")),
    ],
)
def test_detect_platform(url, html, expected):
    assert detect_platform(url, html) == expected


def test_workday_posted_parsing():
    assert _workday_posted("Posted Today") is not None
    assert _workday_posted("Posted 30+ Days Ago") < _workday_posted("Posted 3 Days Ago")
    assert _workday_posted("") is None


def test_platform_note_roundtrip():
    c = Company("X", "Cat", "A", "India", "tech", "manual", "", "", "Denmark bridge")
    c.set_platform("Taleo")
    assert c.platform == "Taleo" and "Denmark bridge" in c.notes
    c.set_platform("")
    assert c.platform == "" and c.notes == "Denmark bridge"


def test_build_page_escapes_script_close(tmp_path):
    c = Company("Evil</script><script>alert(1)</script>", "Cat", "A", "India", "tech", "", "", "", "")
    out = build_page([c], {"A": 10}, tmp_path / "companies.html")
    text = out.read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in text
