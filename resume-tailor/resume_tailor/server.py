import json
import logging
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .config import ROOT, resolve
from .docx_writer import file_name, render_text, write_docx
from .engine import tailor
from .master import load_master
from .ui import PAGE

log = logging.getLogger(__name__)

MAX_BODY = 300_000
MASTER_PATH = ROOT / "resume" / "master.yaml"
OUT_DIR = ROOT / "out"


def request_allowed(host: str | None, origin: str | None, port: int) -> bool:
    """Only same-origin requests to localhost: blocks other websites and DNS-rebinding tricks."""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    return host in hosts and (origin is None or origin in {f"http://{h}" for h in hosts})


def load_job(key: str, jobs_path: Path) -> dict:
    """Prefill from the job-alerts project's job history (title, company, JD)."""
    if not key or not jobs_path.exists():
        return {}
    job = json.loads(jobs_path.read_text(encoding="utf-8")).get(key) or {}
    return {k: job.get(k, "") for k in ("title", "company", "url", "description")}


def status(cfg: dict) -> dict:
    info = {"ai": bool(os.getenv("GEMINI_API_KEY")), "model": (cfg.get("tailor") or {}).get("model", "gemini-2.5-flash")}
    try:
        info["placeholders"] = load_master(MASTER_PATH).placeholders()
        info["master"] = True
    except (OSError, ValueError, KeyError, TypeError) as exc:
        info.update(master=False, error=str(exc), placeholders=[])
    return info


def make_handler(cfg: dict, port: int):
    files: dict[str, Path] = {}
    jobs_path = resolve((cfg.get("tailor") or {}).get("jobs_json", "../job-alerts/data/jobs.json"))

    class Handler(BaseHTTPRequestHandler):
        server_version = "ResumeTailor"

        def log_message(self, fmt, *args):
            log.info(fmt, *args)

        def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _allowed(self) -> bool:
            if request_allowed(self.headers.get("Host"), self.headers.get("Origin"), port):
                return True
            self._json(403, {"error": "forbidden"})
            return False

        def do_GET(self):
            if not self._allowed():
                return
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/api/status":
                self._json(200, status(cfg))
            elif url.path == "/api/job":
                self._json(200, load_job(query.get("key", [""])[0], jobs_path))
            elif url.path == "/api/download":
                path = files.get(query.get("id", [""])[0])
                if not path or not path.exists():
                    self._json(404, {"error": "file not found - generate again"})
                    return
                disposition = f"attachment; filename*=UTF-8''{quote(path.name)}"
                self._send(200, path.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", {"Content-Disposition": disposition})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._allowed():
                return
            if urlparse(self.path).path != "/api/tailor":
                self._json(404, {"error": "not found"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._json(415, {"error": "expected application/json"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error": "request too large"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except ValueError:
                self._json(400, {"error": "invalid JSON"})
                return

            jd = str(payload.get("jd", "")).strip()
            title = str(payload.get("title", "")).strip()[:150]
            company = str(payload.get("company", "")).strip()[:150]
            if len(jd) < 200:
                self._json(400, {"error": "Paste the full job description (at least a few paragraphs)."})
                return
            try:
                master = load_master(MASTER_PATH)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._json(400, {"error": f"Could not load resume/master.yaml: {exc}"})
                return

            result = tailor(master, jd, title, company, cfg, bool(payload.get("exact_title", True)), bool(payload.get("use_ai", True)))
            path = write_docx(result.resume, OUT_DIR / file_name(result.resume, company), cfg.get("template"))
            file_id = secrets.token_urlsafe(12)
            files[file_id] = path
            self._json(200, {
                "mode": result.mode,
                "coverage_before": result.coverage_before,
                "coverage_after": result.coverage_after,
                "keyword_count": result.keyword_count,
                "keyword_target": (cfg.get("tailor") or {}).get("keyword_target", [25, 35]),
                "jd_keywords": result.jd_keywords,
                "matched": result.matched,
                "not_shown": result.not_shown,
                "not_in_master": result.not_in_master,
                "other_terms": result.other_terms,
                "warnings": result.warnings,
                "preview": render_text(result.resume),
                "file": path.name,
                "saved_to": str(path),
                "download": f"/api/download?id={file_id}",
            })

    return Handler


def serve(cfg: dict, open_browser: bool = True) -> int:
    port = int((cfg.get("tailor") or {}).get("port", 8765))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"Resume tailor running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
