import json
from pathlib import Path

from .companies import ROTATION_START, Company


def build_page(companies: list[Company], rotation_days: dict, out_path: Path) -> Path:
    data = [
        {
            "company": c.company,
            "category": c.category,
            "priority": c.priority or "C",
            "auto": c.is_auto,
            "ats": c.ats if c.is_auto else "manual",
            "platform": c.platform,
            "notes": c.notes,
            "links": list(c.links().items()),
        }
        for c in companies
    ]
    payload = {"companies": data, "rotation": rotation_days, "start": ROTATION_START.isoformat()}
    # Escape "</" so company data can never close the <script> block.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out_path.write_text(_TEMPLATE.replace("__PAYLOAD__", blob), encoding="utf-8")
    return out_path


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Target Companies - Careers Pages</title>
<style>
  :root { --bg:#f5f7fb; --card:#fff; --text:#1d2433; --muted:#5b6475; --border:#dde3ee; --accent:#3b6cf6; --ok:#1f9d55; --okbg:#e3f6ea; --due:#f59e0b; }
  body.dark { --bg:#0f1420; --card:#171e2e; --text:#e6eaf2; --muted:#9aa4b8; --border:#2a3448; --accent:#6d8dff; --ok:#34d399; --okbg:#133328; --due:#fbbf24; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); }
  header { position:sticky; top:0; z-index:5; background:var(--card); border-bottom:1px solid var(--border); padding:12px 20px; }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; max-width:1250px; margin:0 auto; }
  h1 { font-size:1.2rem; margin:0; flex:1 1 auto; }
  .stats { font-size:.82rem; color:var(--muted); }
  input, select, button { font:inherit; font-size:.85rem; padding:6px 10px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); }
  button { cursor:pointer; }
  main { max-width:1250px; margin:0 auto; padding:16px 20px 60px; }
  h2 { font-size:1rem; margin:20px 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:10px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
  .card.due { box-shadow:0 0 0 2px var(--due); }
  .card.checked { background:var(--okbg); }
  .name { font-weight:600; }
  .badges { margin:4px 0; display:flex; gap:4px; flex-wrap:wrap; }
  .b { font-size:.66rem; font-weight:700; padding:1px 6px; border-radius:4px; background:var(--border); color:var(--text); }
  .b.pA { background:#dc2626; color:#fff; } .b.pB { background:#f59e0b; color:#111; } .b.pC { background:#6b7280; color:#fff; }
  .b.auto { background:#d1fae5; color:#065f46; } .b.man { background:#e0e7ff; color:#3730a3; }
  .links a { font-size:.82rem; margin-right:10px; color:var(--accent); }
  .meta { font-size:.75rem; color:var(--muted); margin-top:6px; display:flex; justify-content:space-between; align-items:center; gap:6px; }
  .meta button { font-size:.72rem; padding:3px 8px; }
  .empty { color:var(--muted); font-size:.9rem; }
</style>
</head>
<body>
<header>
  <div class="row">
    <h1>Target companies &middot; careers pages</h1>
    <span class="stats" id="stats"></span>
    <button id="theme" type="button">Dark mode</button>
  </div>
  <div class="row" style="margin-top:8px">
    <input id="q" placeholder="Search company..." aria-label="Search company">
    <select id="cat" aria-label="Category"><option value="">All categories</option></select>
    <select id="pri" aria-label="Priority"><option value="">All priorities</option><option>A</option><option>B</option><option>C</option></select>
    <select id="mode" aria-label="Mode">
      <option value="">Auto + manual</option><option value="manual">Manual only</option><option value="auto">Auto only</option>
    </select>
  </div>
</header>
<main>
  <h2 id="dueTitle"></h2>
  <div class="grid" id="due"></div>
  <div id="all"></div>
</main>
<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
(function () {
  "use strict";
  var KEY = "companyChecks.v1", THEME = "companyChecks.theme";
  var P = JSON.parse(document.getElementById("payload").textContent);
  var checks = {};
  try { checks = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { checks = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(checks)); } catch (e) {} }

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var todayStr = today.getFullYear() + "-" + pad(today.getMonth() + 1) + "-" + pad(today.getDate());
  var sp = P.start.split("-").map(Number);
  var dayIdx = Math.round((today - new Date(sp[0], sp[1] - 1, sp[2])) / 86400000);

  function codeSum(s) { var n = 0; for (var i = 0; i < s.length; i++) n += s.charCodeAt(i); return n; }
  function isDue(c) {
    if (c.auto) return false;
    var p = Number(P.rotation[c.priority] || 14);
    return ((dayIdx % p) + p) % p === codeSum(c.company) % p;
  }
  function daysSince(c) {
    var v = checks[c.company];
    if (!v) return null;
    var d = v.split("-").map(Number);
    return Math.round((today - new Date(d[0], d[1] - 1, d[2])) / 86400000);
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function card(c) {
    var ds = daysSince(c);
    var box = el("div", "card" + (isDue(c) ? " due" : "") + (ds === 0 ? " checked" : ""));
    box.appendChild(el("div", "name", c.company));
    var badges = el("div", "badges");
    badges.appendChild(el("span", "b p" + c.priority, c.priority));
    badges.appendChild(el("span", c.auto ? "b auto" : "b man", c.auto ? "AUTO \\u00b7 " + c.ats : "MANUAL" + (c.platform ? " \\u00b7 " + c.platform : "")));
    badges.appendChild(el("span", "b", c.category));
    box.appendChild(badges);
    var links = el("div", "links");
    c.links.forEach(function (l) {
      if (!/^https?:\\/\\//.test(l[1])) return;
      var a = el("a", null, l[0] + " \\u2197");
      a.href = l[1]; a.target = "_blank"; a.rel = "noopener noreferrer";
      links.appendChild(a);
    });
    box.appendChild(links);
    var meta = el("div", "meta");
    meta.appendChild(el("span", null, ds === null ? "never checked" : ds === 0 ? "checked today" : "checked " + ds + " day(s) ago"));
    var btn = el("button", null, ds === 0 ? "Undo" : "Mark checked");
    btn.type = "button";
    btn.addEventListener("click", function () {
      if (ds === 0) delete checks[c.company]; else checks[c.company] = todayStr;
      save(); render();
    });
    meta.appendChild(btn);
    box.appendChild(meta);
    return box;
  }

  var q = document.getElementById("q"), cat = document.getElementById("cat"),
      pri = document.getElementById("pri"), mode = document.getElementById("mode");
  var cats = [];
  P.companies.forEach(function (c) { if (cats.indexOf(c.category) < 0) cats.push(c.category); });
  cats.forEach(function (c) { var o = el("option", null, c); o.value = c; cat.appendChild(o); });

  function matches(c) {
    if (q.value && c.company.toLowerCase().indexOf(q.value.toLowerCase()) < 0) return false;
    if (cat.value && c.category !== cat.value) return false;
    if (pri.value && c.priority !== pri.value) return false;
    if (mode.value === "auto" && !c.auto) return false;
    if (mode.value === "manual" && c.auto) return false;
    return true;
  }

  function render() {
    var due = P.companies.filter(isDue);
    var dueBox = document.getElementById("due");
    dueBox.textContent = "";
    var dueDone = due.filter(function (c) { return daysSince(c) === 0; }).length;
    document.getElementById("dueTitle").textContent = "Due today: " + due.length + " manual careers pages (" + dueDone + " checked)";
    due.forEach(function (c) { dueBox.appendChild(card(c)); });
    if (!due.length) dueBox.appendChild(el("p", "empty", "Nothing due today."));

    var all = document.getElementById("all");
    all.textContent = "";
    cats.forEach(function (name) {
      var list = P.companies.filter(function (c) { return c.category === name && matches(c); });
      if (!list.length) return;
      all.appendChild(el("h2", null, name + " (" + list.length + ")"));
      var grid = el("div", "grid");
      list.forEach(function (c) { grid.appendChild(card(c)); });
      all.appendChild(grid);
    });

    var autoN = P.companies.filter(function (c) { return c.auto; }).length;
    var checkedToday = Object.keys(checks).filter(function (k) { return checks[k] === todayStr; }).length;
    document.getElementById("stats").textContent =
      P.companies.length + " companies \\u00b7 " + autoN + " auto \\u00b7 " + (P.companies.length - autoN) + " manual \\u00b7 " + checkedToday + " checked today";
  }

  [q, cat, pri, mode].forEach(function (e) { e.addEventListener("input", render); });

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
