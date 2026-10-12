import html
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import requests

from .models import Job

log = logging.getLogger(__name__)

TIMEOUT = 20
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (personal-job-alerts/1.0; one run per day)",
    "Accept": "application/json",
})

# SmartRecruiters returns ISO country codes; expand the ones used in location matching.
_COUNTRY_NAMES = {"in": "India", "dk": "Denmark"}


def _request_json(method: str, url: str, params: dict | None = None, body: dict | None = None):
    """JSON request with small retry/backoff. Returns None on 4xx-not-found or persistent failure."""
    for attempt in range(3):
        try:
            resp = _session.request(method, url, params=params, json=body, timeout=TIMEOUT)
            if resp.status_code in (400, 403, 404, 422):
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("%s %s failed (%s), attempt %d", method, url, exc, attempt + 1)
            time.sleep(2 ** attempt)
    return None


def _get_json(url: str, params: dict | None = None):
    return _request_json("GET", url, params=params)


def get_page(url: str) -> tuple[str, str] | None:
    """Fetch a careers page as HTML; returns (final_url_after_redirects, html)."""
    try:
        resp = _session.get(url, timeout=TIMEOUT, headers={"Accept": "text/html,application/xhtml+xml"})
        return resp.url, resp.text[:3_000_000]
    except requests.RequestException as exc:
        log.warning("GET %s failed (%s)", url, exc)
        return None


def _strip_html(text: str | None) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", ". ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_greenhouse(token: str) -> list[Job] | None:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"})
    if data is None:
        return None
    return [
        Job(
            source="greenhouse",
            company=j.get("company_name") or token,
            job_id=str(j.get("id")),
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=_strip_html(j.get("content")),
            posted_at=_parse_dt(j.get("updated_at")),
        )
        for j in data.get("jobs", [])
    ]


def fetch_lever(token: str) -> list[Job] | None:
    data = _get_json(f"https://api.lever.co/v0/postings/{token}", {"mode": "json"})
    if data is None:
        data = _get_json(f"https://api.eu.lever.co/v0/postings/{token}", {"mode": "json"})
    if data is None:
        return None
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        if j.get("workplaceType") == "remote":
            location += " | Remote"
        lists = " ".join(_strip_html(item.get("content")) for item in j.get("lists") or [])
        jobs.append(
            Job(
                source="lever",
                company=token,
                job_id=str(j.get("id")),
                title=j.get("text", ""),
                location=location,
                url=j.get("hostedUrl", ""),
                description=f"{j.get('descriptionPlain', '')} {lists}",
                posted_at=_parse_dt(j.get("createdAt")),
            )
        )
    return jobs


def fetch_ashby(token: str) -> list[Job] | None:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    if data is None:
        return None
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locations = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        location = " | ".join(loc for loc in locations if loc)
        if j.get("isRemote"):
            location += " | Remote"
        url = j.get("jobUrl") or j.get("applyUrl") or ""
        jobs.append(
            Job(
                source="ashby",
                company=token,
                job_id=str(j.get("id") or url),
                title=j.get("title", ""),
                location=location,
                url=url,
                description=j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml")),
                posted_at=_parse_dt(j.get("publishedAt")),
            )
        )
    return jobs


def fetch_smartrecruiters(token: str, title_ok: Callable[[str], bool]) -> list[Job] | None:
    """Descriptions need one extra call per posting, so only fetch them for relevant titles."""
    jobs: list[Job] = []
    offset = 0
    while True:
        data = _get_json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", {"limit": 100, "offset": offset})
        if data is None:
            return None if offset == 0 else jobs
        content = data.get("content", [])
        for j in content:
            title = j.get("name", "")
            if not title_ok(title):
                continue
            loc = j.get("location") or {}
            country = _COUNTRY_NAMES.get((loc.get("country") or "").lower(), loc.get("country"))
            location = ", ".join(x for x in (loc.get("city"), loc.get("region"), country) if x)
            if loc.get("remote"):
                location += " | Remote"
            description = ""
            detail = _get_json(j["ref"]) if j.get("ref") else None
            if detail:
                sections = (detail.get("jobAd") or {}).get("sections") or {}
                description = " ".join(
                    _strip_html((sections.get(k) or {}).get("text"))
                    for k in ("jobDescription", "qualifications", "additionalInformation")
                )
            jobs.append(
                Job(
                    source="smartrecruiters",
                    company=(j.get("company") or {}).get("name") or token,
                    job_id=str(j.get("id")),
                    title=title,
                    location=location,
                    url=f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}",
                    description=description,
                    posted_at=_parse_dt(j.get("releasedDate")),
                )
            )
        offset += len(content)
        if not content or offset >= data.get("totalFound", 0):
            return jobs


def _workday_posted(text: str | None) -> datetime | None:
    """Workday only gives 'Posted Today' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago'."""
    t = (text or "").lower()
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    else:
        match = re.search(r"(\d+)(\+)?\s*days?", t)
        if not match:
            return None
        days = int(match.group(1)) + (1 if match.group(2) else 0)
    return datetime.now(timezone.utc) - timedelta(days=days)


def fetch_workday(ats_id: str, queries: list[str], pages: int, title_ok: Callable[[str], bool]) -> list[Job] | None:
    """ats_id = 'tenant|wdN|site'. Uses the JSON endpoint the Workday careers page itself calls."""
    try:
        tenant, wd, site = ats_id.split("|")
    except ValueError:
        log.warning("Bad Workday id '%s' (expected tenant|wdN|site)", ats_id)
        return None
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{host}/wday/cxs/{tenant}/{site}"
    jobs: dict[str, Job] = {}
    reachable = False
    for query in queries:
        for page in range(pages):
            body = {"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": query}
            data = _request_json("POST", f"{api}/jobs", body=body)
            if data is None:
                break
            reachable = True
            postings = data.get("jobPostings") or []
            for p in postings:
                path, title = p.get("externalPath", ""), p.get("title", "")
                if not path or path in jobs or not title_ok(title):
                    continue
                info = (_get_json(f"{api}{path}") or {}).get("jobPostingInfo") or {}
                locations = [p.get("locationsText", ""), info.get("location", ""), *(info.get("additionalLocations") or [])]
                jobs[path] = Job(
                    source="workday",
                    company=tenant,
                    job_id=path,
                    title=title,
                    location=" | ".join(loc for loc in locations if loc),
                    url=f"{host}/{site}{path}",
                    description=_strip_html(info.get("jobDescription")),
                    posted_at=_workday_posted(p.get("postedOn")),
                )
            if len(postings) < 20:
                break
            time.sleep(0.5)
    return list(jobs.values()) if reachable else None


def fetch_adzuna(app_id: str, app_key: str, country: str, query: str, max_days_old: int, pages: int) -> list[Job]:
    jobs = []
    for page in range(1, pages + 1):
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "results_per_page": 50,
            "max_days_old": max_days_old,
            "sort_by": "date",
            "content-type": "application/json",
        }
        data = _get_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params)
        if not data:
            break
        results = data.get("results", [])
        suffix = _COUNTRY_NAMES.get(country, "")
        for j in results:
            location = (j.get("location") or {}).get("display_name", "")
            jobs.append(
                Job(
                    source="adzuna",
                    company=(j.get("company") or {}).get("display_name", "Unknown"),
                    job_id=str(j.get("id")),
                    title=_strip_html(j.get("title")),
                    location=f"{location}, {suffix}" if suffix else location,
                    url=j.get("redirect_url", ""),
                    description=_strip_html(j.get("description")),
                    posted_at=_parse_dt(j.get("created")),
                )
            )
        if len(results) < 50:
            break
        time.sleep(1)
    return jobs
