import argparse
import logging
import time
from collections.abc import Callable

from . import sources
from .companies import Company, detect_platform, due_today, load_companies, save_companies
from .config import ROOT, env, load_config
from .digest import build_jobs_page
from .filters import Filters
from .models import Job
from .page import build_page
from .resume import load_resume_skills, score_job
from .store import JobHistory

log = logging.getLogger("job_alerts")


def fetch_board(ats: str, ats_id: str, title_ok: Callable[[str], bool], cfg: dict) -> list[Job] | None:
    if ats == "greenhouse":
        return sources.fetch_greenhouse(ats_id)
    if ats == "lever":
        return sources.fetch_lever(ats_id)
    if ats == "ashby":
        return sources.fetch_ashby(ats_id)
    if ats == "smartrecruiters":
        return sources.fetch_smartrecruiters(ats_id, title_ok)
    if ats == "workday":
        wd = cfg.get("workday") or {}
        return sources.fetch_workday(ats_id, wd.get("queries", ["AI"]), wd.get("pages", 1), title_ok)
    log.warning("Unknown ATS '%s' in companies.csv", ats)
    return None


def _no_titles(_title: str) -> bool:
    return False


def companies_path(cfg: dict):
    return ROOT / cfg.get("companies_csv", "companies.csv")


def collect(cfg: dict, filters: Filters, companies: list[Company]) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    failed: list[str] = []
    for c in companies:
        if not c.is_auto:
            continue
        profile = c.title_profile or "tech"
        result = fetch_board(c.ats, c.ats_id, lambda t, p=profile: filters.title_ok(t, p), cfg)
        if result is None:
            failed.append(c.company)
            continue
        for job in result:
            job.company = c.company
            job.title_profile = profile
        jobs.extend(result)
        time.sleep(0.5)

    adz = cfg.get("adzuna") or {}
    if adz.get("enabled"):
        app_id, app_key = env("ADZUNA_APP_ID"), env("ADZUNA_APP_KEY")
        for country in adz.get("countries", ["in"]):
            for query in adz.get("queries", []):
                jobs.extend(
                    sources.fetch_adzuna(app_id, app_key, country, query, adz.get("max_days_old", 3), adz.get("pages", 1))
                )
    return jobs, failed


def validate(cfg: dict, companies: list[Company]) -> int:
    missing = 0
    for c in companies:
        if not c.is_auto:
            continue
        result = fetch_board(c.ats, c.ats_id, _no_titles, cfg)
        if result is None:
            missing += 1
            print(f"NOT FOUND   {c.ats:<16} {c.ats_id:<40} {c.company}")
        else:
            count = "n/a" if c.ats in ("smartrecruiters", "workday") else str(len(result))
            print(f"OK {count:>5}    {c.ats:<16} {c.ats_id:<40} {c.company}")
        time.sleep(0.5)
    print(f"\n{missing} automatic board(s) failed - run --detect to re-check them")
    return 1 if missing else 0


def detect(cfg: dict, companies: list[Company]) -> int:
    """Find which careers pages use a readable platform; writes ats/ats_id/notes back to companies.csv."""
    for c in companies:
        if c.is_auto and fetch_board(c.ats, c.ats_id, _no_titles, cfg) is not None:
            c.notes = c.notes.replace("prefilled - verify", "verified")
            print(f"AUTO    {c.ats:<16} {c.company}")
            continue
        if not c.careers_url:
            ats, ats_id, platform = "manual", "", "no careers_url"
        else:
            page = sources.get_page(c.careers_url)
            ats, ats_id, platform = detect_platform(*page) if page else ("manual", "", "unreachable")
            if ats != "manual" and fetch_board(ats, ats_id, _no_titles, cfg) is None:
                ats, ats_id, platform = "manual", "", f"{ats} detected but API failed"
            time.sleep(0.5)
        c.ats, c.ats_id = ats, ats_id
        c.set_platform(platform)
        print(f"{'AUTO' if ats != 'manual' else 'MANUAL':<7} {ats if ats != 'manual' else platform:<16} {c.company}")

    save_companies(companies_path(cfg), companies)
    auto = sum(c.is_auto for c in companies)
    print(f"\nSaved companies.csv: {auto} automatic, {len(companies) - auto} manual")
    return 0


def run(cfg: dict, companies: list[Company], dry_run: bool) -> int:
    filters = Filters(cfg)
    jobs, failed = collect(cfg, filters, companies)
    unique = list({j.key: j for j in jobs}.values())
    history = JobHistory(ROOT / "data" / "jobs.json", cfg.get("seen_retention_days", 180))
    resume_skills, vocab = load_resume_skills(cfg)

    new_jobs = 0
    for job in unique:
        if not filters.accept(job) or not history.is_new(job.key):
            continue
        score_job(job, resume_skills, vocab)
        history.add(job)
        new_jobs += 1
    log.info("Fetched %d jobs (%d unique) -> %d new matches; %d boards failed", len(jobs), len(unique), new_jobs, len(failed))

    out_dir = ROOT / "out" if dry_run else ROOT
    out_dir.mkdir(exist_ok=True)
    rotation = cfg.get("rotation_days") or {}
    due = due_today(companies, rotation)
    build_page(companies, rotation, out_dir / "companies.html")
    show_days = (cfg.get("page") or {}).get("show_days", 14)
    jobs_page = build_jobs_page(history.recent(show_days), new_jobs, due, failed, show_days, out_dir / "jobs.html")

    if dry_run:
        log.info("Dry run: wrote %s (job history not saved)", jobs_page)
        return 0
    history.save()
    log.info("Wrote %s (%d new jobs, %d careers pages due today)", jobs_page, new_jobs, len(due))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job_alerts", description="Daily AI job finder (0-3 YOE) -> jobs.html")
    parser.add_argument("--dry-run", action="store_true", help="write pages to out/ without saving job history")
    parser.add_argument("--validate", action="store_true", help="check every automatic board in companies.csv")
    parser.add_argument("--detect", action="store_true", help="detect careers-page platforms and update companies.csv")
    parser.add_argument("--build-page", action="store_true", help="only regenerate companies.html")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    companies = load_companies(companies_path(cfg))
    if args.validate:
        return validate(cfg, companies)
    if args.detect:
        return detect(cfg, companies)
    if args.build_page:
        out = build_page(companies, cfg.get("rotation_days") or {}, ROOT / "companies.html")
        print(f"Wrote {out}")
        return 0
    try:
        return run(cfg, companies, args.dry_run)
    except Exception:
        log.exception("Run failed")
        return 1
