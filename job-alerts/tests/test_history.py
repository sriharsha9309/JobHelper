from datetime import datetime, timezone

from job_alerts.digest import build_jobs_page
from job_alerts.models import Job
from job_alerts.store import JobHistory


def _job(key_id="1", title="AI Engineer"):
    return Job(source="t", company="acme", job_id=key_id, title=title, location="Pune", url="https://x/1",
               posted_at=datetime.now(timezone.utc), location_label="Pune", score=80)


def test_history_dedupes_and_persists(tmp_path):
    path = tmp_path / "jobs.json"
    history = JobHistory(path)
    job = _job()
    assert history.is_new(job.key)
    history.add(job)
    history.add(job)
    history.save()

    reloaded = JobHistory(path)
    assert not reloaded.is_new(job.key)
    assert [e["title"] for e in reloaded.recent(14)] == ["AI Engineer"]


def test_jobs_page_escapes_script_close(tmp_path):
    history = JobHistory(tmp_path / "jobs.json")
    history.add(_job(title="x</script><script>alert(1)</script>"))
    out = build_jobs_page(history.recent(14), 1, [], [], 14, tmp_path / "jobs.html")
    assert "</script><script>alert(1)" not in out.read_text(encoding="utf-8")
