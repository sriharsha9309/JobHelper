import json
from pathlib import Path

from .companies import Company


def build_jobs_page(
    entries: list[dict], new_today: int, due: list[Company], failed_boards: list[str], show_days: int, out_path: Path
) -> Path:
    payload = {
        "jobs": entries,
        "newToday": new_today,
        "days": show_days,
        "due": [c.company for c in due],
        "failed": failed_boards,
    }
    # Escape "</" so job data can never close the <script> block.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out_path.write_text(_TEMPLATE.replace("__PAYLOAD__", blob), encoding="utf-8")
    return out_path


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Jobs (0-3 YOE)</title>
<style>
  :root { --bg:#f5f7fb; --card:#fff; --text:#1d2433; --muted:#5b6475; --border:#dde3ee; --accent:#3b6cf6; --new:#f59e0b; --ok:#1f9d55; --okbg:#e3f6ea; }
  body.dark { --bg:#0f1420; --card:#171e2e; --text:#e6eaf2; --muted:#9aa4b8; --border:#2a3448; --accent:#6d8dff; --new:#fbbf24; --ok:#34d399; --okbg:#133328; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); }
  header { position:sticky; top:0; z-index:5; background:var(--card); border-bottom:1px solid var(--border); padding:12px 20px; }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; max-width:1250px; margin:0 auto; }
  h1 { font-size:1.2rem; margin:0; flex:1 1 auto; }
  .sub { font-size:.82rem; color:var(--muted); }
  input, select, button { font:inherit; font-size:.85rem; padding:6px 10px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); }
  button { cursor:pointer; }
  main { max-width:1250px; margin:0 auto; padding:12px 20px 60px; }
  .notice { font-size:.85rem; margin:8px 0; }
  .notice a { color:var(--accent); }
  .warn { color:#b45309; font-size:.8rem; }
  h2 { font-size:.95rem; margin:18px 0 8px; color:var(--muted); }
  table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
  th, td { padding:7px 9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; font-size:.85rem; }
  th { font-size:.75rem; color:var(--muted); background:var(--bg); }
  tr.applied { background:var(--okbg); }
  tr.dismissed { opacity:.45; }
  td a { color:var(--accent); font-weight:600; }
  .skills { font-size:.72rem; color:var(--muted); margin-top:2px; }
  .new { font-size:.65rem; font-weight:800; padding:1px 6px; border-radius:4px; background:var(--new); color:#111; margin-left:6px; }
  .acts button { font-size:.72rem; padding:3px 7px; margin:0 3px 3px 0; }
  .empty { color:var(--muted); }
</style>
</head>
<body>
<header>
  <div class="row">
    <h1>AI jobs &middot; 0-3 YOE</h1>
    <span class="sub" id="stats"></span>
    <button id="theme" type="button">Dark mode</button>
  </div>
  <div class="row" style="margin-top:8px">
    <input id="q" placeholder="Search title / company..." aria-label="Search">
    <select id="view" aria-label="View">
      <option value="open">Open (hide dismissed)</option>
      <option value="new">New today only</option>
      <option value="applied">Applied</option>
      <option value="all">All</option>
    </select>
    <select id="sort" aria-label="Sort">
      <option value="score">Sort: match %</option>
      <option value="date">Sort: newest</option>
    </select>
  </div>
</header>
<main>
  <p class="notice" id="dueNote"></p>
  <p class="warn" id="failed"></p>
  <div id="list"></div>
</main>
<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
(function () {
  "use strict";
  var KEY = "jobStatus.v1", THEME = "companyChecks.theme";
  var P = JSON.parse(document.getElementById("payload").textContent);
  var status = {};
  try { status = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { status = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(status)); } catch (e) {} }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  var d = new Date();
  var todayStr = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  function localDay(iso) {
    var t = new Date(iso);
    return t.getFullYear() + "-" + pad(t.getMonth() + 1) + "-" + pad(t.getDate());
  }

  var due = document.getElementById("dueNote");
  due.textContent = P.due.length + " careers pages are due today: " + P.due.slice(0, 8).join(", ") + (P.due.length > 8 ? ", ..." : "") + " ";
  var link = el("a", null, "Open companies.html \\u2192");
  link.href = "companies.html";
  due.appendChild(link);
  if (P.failed.length) document.getElementById("failed").textContent = "Automatic boards that failed on the last run: " + P.failed.join(", ");

  var q = document.getElementById("q"), view = document.getElementById("view"), sort = document.getElementById("sort");

  function visible(j) {
    var s = status[j.key];
    if (q.value) {
      var hay = (j.title + " " + j.company).toLowerCase();
      if (hay.indexOf(q.value.toLowerCase()) < 0) return false;
    }
    if (view.value === "open") return s !== "dismissed";
    if (view.value === "new") return localDay(j.first_seen) === todayStr && s !== "dismissed";
    if (view.value === "applied") return s === "applied";
    return true;
  }

  function setStatus(key, value) {
    if (status[key] === value) delete status[key]; else status[key] = value;
    save(); render();
  }

  function row(j) {
    var s = status[j.key];
    var tr = el("tr", s || "");
    var isNew = localDay(j.first_seen) === todayStr;
    tr.appendChild(el("td", null, j.score == null ? "-" : j.score + "%"));
    var td = el("td");
    if (/^https?:\\/\\//.test(j.url)) {
      var a = el("a", null, j.title);
      a.href = j.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      td.appendChild(a);
    } else {
      td.appendChild(el("span", null, j.title));
    }
    if (isNew) td.appendChild(el("span", "new", "NEW"));
    if ((j.matched_skills || []).length || (j.missing_skills || []).length) {
      td.appendChild(el("div", "skills", "match: " + ((j.matched_skills || []).join(", ") || "-") + "  |  gap: " + ((j.missing_skills || []).join(", ") || "-")));
    }
    tr.appendChild(td);
    tr.appendChild(el("td", null, j.company));
    tr.appendChild(el("td", null, j.location_label));
    tr.appendChild(el("td", null, j.min_years == null ? "not stated" : j.min_years + "+ yrs"));
    tr.appendChild(el("td", null, j.posted_at ? localDay(j.posted_at).slice(5) : "-"));
    var acts = el("td", "acts");
    [["applied", s === "applied" ? "Unmark" : "Applied"], ["dismissed", s === "dismissed" ? "Restore" : "Dismiss"]].forEach(function (b) {
      var btn = el("button", null, b[1]);
      btn.type = "button";
      btn.addEventListener("click", function () { setStatus(j.key, b[0]); });
      acts.appendChild(btn);
    });
    tr.appendChild(acts);
    return tr;
  }

  function render() {
    var list = P.jobs.filter(visible);
    list.sort(function (a, b) {
      if (sort.value === "date") return b.first_seen.localeCompare(a.first_seen);
      return (b.score == null ? -1 : b.score) - (a.score == null ? -1 : a.score);
    });
    var box = document.getElementById("list");
    box.textContent = "";
    if (!list.length) { box.appendChild(el("p", "empty", "No jobs for this view.")); }
    else {
      var table = el("table");
      var head = el("tr");
      ["Match", "Role", "Company", "Location", "Exp", "Posted", ""].forEach(function (h) { head.appendChild(el("th", null, h)); });
      table.appendChild(head);
      list.forEach(function (j) { table.appendChild(row(j)); });
      box.appendChild(table);
    }
    var applied = P.jobs.filter(function (j) { return status[j.key] === "applied"; }).length;
    document.getElementById("stats").textContent =
      P.newToday + " new on last run \\u00b7 " + P.jobs.length + " in last " + P.days + " days \\u00b7 " + applied + " applied";
  }

  [q, view, sort].forEach(function (e) { e.addEventListener("input", render); });

  function applyTheme(dark) {
    document.body.classList.toggle("dark", dark);
    document.getElementById("theme").textContent = dark ? "Light mode" : "Dark mode";
  }
  var storedTheme = localStorage.getItem(THEME);
  applyTheme(storedTheme ? storedTheme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme").addEventListener("click", function () {
    var dark = !document.body.classList.contains("dark");
    localStorage.setItem(THEME, dark ? "dark" : "light");
    applyTheme(dark);
  });

  render();
})();
</script>
</body>
</html>
"""
