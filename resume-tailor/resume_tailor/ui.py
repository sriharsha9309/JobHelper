PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resume Tailor</title>
<style>
  :root { --bg:#f5f7fb; --card:#fff; --text:#1d2433; --muted:#5b6475; --border:#dde3ee; --accent:#3b6cf6; --ok:#1f9d55; --warn:#b45309; --bad:#dc2626; }
  body.dark { --bg:#0f1420; --card:#171e2e; --text:#e6eaf2; --muted:#9aa4b8; --border:#2a3448; --accent:#6d8dff; --ok:#34d399; --warn:#fbbf24; --bad:#f87171; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); }
  header { background:var(--card); border-bottom:1px solid var(--border); padding:12px 20px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  h1 { font-size:1.2rem; margin:0; flex:1; }
  .status { font-size:.8rem; color:var(--muted); }
  main { max-width:1300px; margin:0 auto; padding:16px 20px 60px; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; }
  @media (max-width: 900px) { main { grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; }
  label { font-size:.82rem; color:var(--muted); display:block; margin:8px 0 4px; }
  input[type=text], textarea { width:100%; font:inherit; font-size:.9rem; padding:8px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:var(--text); }
  textarea { min-height:340px; resize:vertical; }
  .row { display:flex; gap:10px; }
  .row > div { flex:1; }
  .checks { margin:10px 0; font-size:.88rem; display:flex; flex-direction:column; gap:6px; }
  button, .btn { font:inherit; cursor:pointer; padding:8px 14px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:#fff; text-decoration:none; display:inline-block; }
  button.secondary { background:transparent; color:var(--text); border-color:var(--border); }
  button:disabled { opacity:.6; cursor:wait; }
  .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px; }
  .stat { border:1px solid var(--border); border-radius:10px; padding:8px; text-align:center; }
  .stat b { display:block; font-size:1.3rem; }
  .stat span { font-size:.72rem; color:var(--muted); }
  .chips { display:flex; flex-wrap:wrap; gap:4px; margin:4px 0 10px; }
  .chip { font-size:.72rem; padding:2px 7px; border-radius:99px; border:1px solid var(--border); }
  .chip.ok { border-color:var(--ok); color:var(--ok); }
  .chip.warn { border-color:var(--warn); color:var(--warn); }
  .chip.bad { border-color:var(--bad); color:var(--bad); }
  h3 { font-size:.85rem; margin:10px 0 2px; }
  .warnings { font-size:.82rem; color:var(--warn); padding-left:18px; }
  pre { white-space:pre-wrap; font-size:.8rem; background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px; max-height:520px; overflow:auto; }
  .err { color:var(--bad); font-size:.88rem; }
  .hint { font-size:.75rem; color:var(--muted); }
  ul.checklist { font-size:.8rem; color:var(--muted); padding-left:18px; margin:6px 0 0; }
</style>
</head>
<body>
<header>
  <h1>Resume Tailor &middot; ATS-friendly DOCX per job</h1>
  <span class="status" id="status">checking...</span>
  <button class="secondary" id="theme" type="button">Dark mode</button>
</header>
<main>
  <section class="card">
    <div class="row">
      <div><label for="title">Exact job title (from the posting)</label><input type="text" id="title" placeholder="e.g. GenAI Engineer"></div>
      <div><label for="company">Company</label><input type="text" id="company" placeholder="e.g. Fractal"></div>
    </div>
    <label for="jd">Job description (paste everything)</label>
    <textarea id="jd" placeholder="Paste the full job description here..."></textarea>
    <div class="checks">
      <label style="margin:0;color:var(--text)"><input type="checkbox" id="exact" checked> Use the exact job title as my resume headline</label>
      <label style="margin:0;color:var(--text)"><input type="checkbox" id="ai" checked> Rewrite with Gemini (fact-checked; falls back to keyword-only)</label>
    </div>
    <button id="go" type="button">Generate tailored resume</button>
    <p class="err" id="err"></p>
    <ul class="checklist">
      <li>Single column, standard headings, contact details in the body, no tables or icons.</li>
      <li>Dates as "Mon YYYY". Output is .docx.</li>
      <li>Only facts from resume/master.yaml are used. Always read the result before sending.</li>
    </ul>
  </section>
  <section class="card" id="result">
    <p class="hint">Results appear here. Each generated file is also saved in resume-tailor/out/.</p>
  </section>
</main>
<script>
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function chips(title, items, cls) {
    var frag = document.createDocumentFragment();
    frag.appendChild(el("h3", null, title + " (" + items.length + ")"));
    var box = el("div", "chips");
    if (!items.length) box.appendChild(el("span", "hint", "none"));
    items.forEach(function (t) { box.appendChild(el("span", "chip " + (cls || ""), t)); });
    frag.appendChild(box);
    return frag;
  }

  fetch("/api/status").then(function (r) { return r.json(); }).then(function (s) {
    var parts = [s.ai ? "Gemini: " + s.model : "Gemini: no API key (keyword-only)"];
    if (!s.master) parts.push("master.yaml missing");
    else if (s.placeholders.length) parts.push(s.placeholders.length + " placeholders in master.yaml");
    else parts.push("master.yaml ready");
    $("status").textContent = parts.join(" \\u00b7 ");
    if (!s.ai) { $("ai").checked = false; }
  }).catch(function () { $("status").textContent = "server not reachable"; });

  var key = new URLSearchParams(location.search).get("job");
  if (key) {
    fetch("/api/job?key=" + encodeURIComponent(key)).then(function (r) { return r.json(); }).then(function (j) {
      if (j.title) $("title").value = j.title;
      if (j.company) $("company").value = j.company;
      if (j.description) $("jd").value = j.description;
      else if (j.title) $("err").textContent = "No saved description for this job - open the posting and paste the JD.";
    });
  }

  function render(d) {
    var box = $("result");
    box.textContent = "";
    var stats = el("div", "stats");
    [[d.coverage_before + "% \\u2192 " + d.coverage_after + "%", "JD keyword coverage"],
     [d.keyword_count + "", "role keywords (target " + d.keyword_target[0] + "-" + d.keyword_target[1] + ")"],
     [d.mode === "ai" ? "AI + checks" : "Keyword-only", "mode"]].forEach(function (s) {
      var c = el("div", "stat"); c.appendChild(el("b", null, s[0])); c.appendChild(el("span", null, s[1])); stats.appendChild(c);
    });
    box.appendChild(stats);
    var a = el("a", "btn", "Download " + d.file);
    a.href = d.download;
    box.appendChild(a);
    box.appendChild(el("p", "hint", "Saved to " + d.saved_to));
    if (d.warnings.length) {
      var ul = el("ul", "warnings");
      d.warnings.forEach(function (w) { ul.appendChild(el("li", null, w)); });
      box.appendChild(ul);
    }
    box.appendChild(chips("JD keywords on your resume", d.matched, "ok"));
    box.appendChild(chips("In your master but not shown - add if relevant", d.not_shown, "warn"));
    box.appendChild(chips("Not in your master - only add if TRUE", d.not_in_master, "bad"));
    box.appendChild(chips("Other JD terms to review", d.other_terms, ""));
    box.appendChild(el("h3", null, "Preview (what an ATS reads)"));
    box.appendChild(el("pre", null, d.preview));
  }

  $("go").addEventListener("click", function () {
    $("err").textContent = "";
    $("go").disabled = true;
    $("go").textContent = $("ai").checked ? "Generating with Gemini..." : "Generating...";
    fetch("/api/tailor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd: $("jd").value, title: $("title").value, company: $("company").value,
                             exact_title: $("exact").checked, use_ai: $("ai").checked })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) { if (!res.ok) throw new Error(res.d.error || "failed"); render(res.d); })
      .catch(function (e) { $("err").textContent = e.message; })
      .finally(function () { $("go").disabled = false; $("go").textContent = "Generate tailored resume"; });
  });

  function applyTheme(dark) {
    document.body.classList.toggle("dark", dark);
    $("theme").textContent = dark ? "Light mode" : "Dark mode";
  }
  var stored = localStorage.getItem("tailor.theme");
  applyTheme(stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  $("theme").addEventListener("click", function () {
    var dark = !document.body.classList.contains("dark");
    localStorage.setItem("tailor.theme", dark ? "dark" : "light");
    applyTheme(dark);
  });
})();
</script>
</body>
</html>
"""
