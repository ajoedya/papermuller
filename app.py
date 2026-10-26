"""
app.py  -  THE SIMPLE WEB INTERFACE
===================================
Double-click "Start.bat" (or run:  python app.py ) and your browser opens
a simple page where you can set keys, type a topic, approve the plan, and
read the results. No terminal typing needed.

It runs ONLY on your own computer (address: http://localhost:8765).
Nothing here is published to the internet.

How it works, in short:
  - This file is a tiny web server built from Python's standard library.
  - The page (ui.html) asks this server to do things, e.g. "make a plan".
  - The server runs the same stages as harness.py, in the background,
    and the page checks every second to show progress.
"""

import csv
import io
import json
import re
import os
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import harness
import llm
import stages
import tools
import sources
import manuscript
import paper
import pipeline
import editorial

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
PROJECTS = HERE / "projects"
PORT = 8765

# Everything the page needs to know about the current job lives here.
STATE = {"phase": "idle", "stage": 0, "log": [], "plan": None, "topic": "",
         "folder": "", "error": "", "requests": 0,
         "completed_steps": [], "events": [], "usage_by_stage": {}, "active_model": "",
         "stage_started": ""}
LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Settings file (.env) helpers
# ---------------------------------------------------------------------------
def ensure_env():
    if not ENV_FILE.exists():
        shutil.copy(HERE / "env.example", ENV_FILE)


def update_env(updates):
    """Change some KEY=value lines in .env, keeping everything else as it is."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in updates:
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    for key, value in updates.items():
        if key not in done:
            lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_settings():
    """Load settings; return (settings, problem message or '')."""
    try:
        return harness.load_settings(), ""
    except (SystemExit, ValueError) as stop:
        return None, str(stop)


# Fields the page may change: request field -> .env key. Values are checked by
# harness.parse_settings before anything is written.
TEXT_FIELDS = {"model": "MODEL", "language": "LANGUAGE", "email": "EMAIL",
               "plan_model": "PLAN_MODEL", "screen_model": "SCREEN_MODEL",
               "evidence_model": "EVIDENCE_MODEL", "outline_model": "OUTLINE_MODEL",
               "writer_model": "WRITER_MODEL", "verifier_model": "VERIFIER_MODEL",
               "review_model": "REVIEW_MODEL", "redteam_model": "REDTEAM_MODEL",
               "paper_model": "PAPER_MODEL", "paper_review_model": "PAPER_REVIEW_MODEL",
               "from_year": "FROM_YEAR", "to_year": "TO_YEAR", "work_type": "WORK_TYPE",
               "min_citations": "MIN_CITATIONS", "candidates": "CANDIDATES",
               "max_papers": "MAX_PAPERS", "min_verified": "MIN_VERIFIED",
               "revision_rounds": "REVISION_ROUNDS", "target": "TARGET_SCORE"}
BOOL_FIELDS = {"demo": "DEMO_MODE", "open_access_only": "OPEN_ACCESS_ONLY", "fetch_fulltext": "FETCH_FULLTEXT", "require_fulltext": "REQUIRE_FULLTEXT"}
RESEARCH_FIELDS = {"from_year", "to_year", "work_type", "open_access_only", "fetch_fulltext", "require_fulltext", "min_citations",
                   "candidates", "max_papers", "min_verified", "revision_rounds", "target", "language"}
MODEL_ID = re.compile(r"[A-Za-z0-9._:/@+\-]+(?:\s*,\s*[A-Za-z0-9._:/@+\-]+)*")


def raw_env():
    raw = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            raw[k.strip()] = v.strip().strip('"')
    return raw


def save_settings(data, allowed=None):
    """Validate a partial settings update, then write only the changed keys."""
    updates = {}
    for field, key in TEXT_FIELDS.items():
        if field in data and (allowed is None or field in allowed):
            value = str(data[field] if data[field] is not None else "").strip()
            if "\n" in value or "\r" in value or len(value) > 300:
                raise ValueError("Invalid settings value.")
            if key.endswith("MODEL") and value and not MODEL_ID.fullmatch(value):
                raise ValueError(f"Invalid model ID for {key}. Use provider/model, comma-separated for fallbacks.")
            updates[key] = value
    for field, key in BOOL_FIELDS.items():
        if field in data and (allowed is None or field in allowed):
            updates[key] = "true" if data[field] else "false"
    if allowed is None:  # API keys are only replaced when the user typed a new one
        for field, key in (("openrouter_key", "OPENROUTER_API_KEY"), ("openalex_key", "OPENALEX_API_KEY")):
            value = str(data.get(field, "") or "").strip()
            if value:
                if len(value) > 300 or any(c.isspace() for c in value):
                    raise ValueError("Invalid API key format.")
                updates[key] = value
    merged = dict(raw_env(), **updates)
    try:
        harness.parse_settings(merged)
    except ValueError as problem:
        # A missing live key is reported, not blocking, so demo users can switch modes later.
        if "OPENROUTER_API_KEY" not in str(problem):
            raise
    if updates:
        update_env(updates)


def public_settings():
    raw = raw_env()
    settings, problem = read_settings()
    data = {"demo": raw.get("DEMO_MODE", "true").lower() == "true",
            "has_openrouter_key": raw.get("OPENROUTER_API_KEY", "").startswith("sk-or-"),
            "has_openalex_key": bool(raw.get("OPENALEX_API_KEY")),
            "fetch_fulltext": raw.get("FETCH_FULLTEXT", "true").lower() == "true",
            "require_fulltext": raw.get("REQUIRE_FULLTEXT", "false").lower() == "true",
            "open_access_only": raw.get("OPEN_ACCESS_ONLY", "false").lower() == "true",
            "problem": problem, "current_year": harness.CURRENT_YEAR}
    for field, key in TEXT_FIELDS.items():
        data[field] = raw.get(key, "")
    if settings:  # show the effective defaults for blank numeric fields
        for field in ("from_year", "to_year", "min_citations", "candidates", "max_papers",
                      "min_verified", "revision_rounds", "work_type"):
            data[field] = settings[TEXT_FIELDS[field]]
        data["target"] = settings["TARGET_SCORE"]
        data["model"] = settings["MODEL"]
    return data


# ---------------------------------------------------------------------------
# Logging: anything the stages print() also goes to the page
# ---------------------------------------------------------------------------
class PageLog(io.TextIOBase):
    def __init__(self, folder=None):
        self.folder = folder

    def write(self, text):
        sys.__stdout__.write(text)
        for line in text.splitlines():
            if line.strip() and not set(line.strip()) <= {"="}:
                stamped = f"[{datetime.now():%H:%M:%S}] {line.strip()}"
                with LOCK:
                    STATE["log"].append(stamped)
                if self.folder:
                    with open(self.folder / "log.txt", "a", encoding="utf-8") as f:
                        f.write(stamped + "\n")
        return len(text)


LLM_STAGE_TO_STEP = {"plan": 1, "screen": 4, "matrix": 5, "outline": 6,
                     "draft": 7, "evidence_audit": 8, "review": 9, "redteam": 9,
                     "paper_draft": 10, "paper_review": 11, "check": 0}


def record_event(kind, step, message, **extra):
    item = {"time": datetime.now().strftime("%H:%M:%S"), "kind": kind,
            "step": step, "message": str(message)[:240], **extra}
    with LOCK:
        STATE["events"].append(item)
        STATE["events"] = STATE["events"][-150:]


def enter_step(step):
    with LOCK:
        previous = STATE.get("stage", 0)
        if 1 <= previous <= len(pipeline.STEPS) and previous != step and previous not in STATE["completed_steps"]:
            STATE["completed_steps"].append(previous)
        STATE["stage"] = step
        STATE["stage_started"] = datetime.now().isoformat(timespec="seconds")
        STATE["active_model"] = ""
    record_event("stage", step, f"Starting: {pipeline.STEPS[step - 1]['name']}")


def on_llm_event(event):
    step = LLM_STAGE_TO_STEP.get(event.get("stage"), 0)
    model = str(event.get("model", ""))[:200]
    usage = event.get("usage") or {}
    values = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
              if isinstance(usage.get(k), (int, float)) and not isinstance(usage.get(k), bool)}
    with LOCK:
        STATE["active_model"] = model
        if step:
            old = STATE["usage_by_stage"].setdefault(str(step), {"calls": 0, "prompt_tokens": 0,
                                                               "completion_tokens": 0, "total_tokens": 0,
                                                               "cost": 0, "has_cost": False, "has_tokens": False})
            old["calls"] += 1
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if k in values:
                    old[k] += values[k]
                    old["has_tokens"] = True
            if "cost" in values:
                old["cost"] += values["cost"]
                old["has_cost"] = True
    record_event("model", step, "Model response received" if not event.get("simulated")
                 else "Demo response received", model=model, simulated=bool(event.get("simulated")),
                 usage=values)


def say(message):
    print(message)


def set_state(**changes):
    with LOCK:
        STATE.update(changes)
        STATE["requests"] = llm.REQUESTS_USED[0]


def run_in_background(job):
    """Run `job` in a separate thread, turning any error into a clear message."""
    def wrapper():
        old = sys.stdout
        old_hook = llm.EVENT_HOOK
        llm.EVENT_HOOK = on_llm_event
        sys.stdout = PageLog(Path(STATE["folder"]) if STATE["folder"] else None)
        try:
            job()
        except SystemExit as stop:
            set_state(phase="failed", error=str(stop).strip() or "The run stopped.")
        except Exception as error:  # unexpected problem: show it instead of crashing
            set_state(phase="failed", error=f"{type(error).__name__}: {error}")
        finally:
            sys.stdout = old
            llm.EVENT_HOOK = old_hook
            set_state()
    threading.Thread(target=wrapper, daemon=True).start()


# ---------------------------------------------------------------------------
# The jobs
# ---------------------------------------------------------------------------
def job_plan(topic):
    settings, problem = read_settings()
    if problem:
        raise SystemExit(problem)
    folder = PROJECTS / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder.mkdir(parents=True, exist_ok=False)
    set_state(folder=str(folder))
    enter_step(1)
    sys.stdout.folder = folder
    say(f"Topic: {topic}")
    say(f"Mode: {'DEMO (fictional sample data)' if settings['DEMO_MODE'] else 'LIVE'}")
    say("Stage 1: preparing the research plan...")
    plan = stages.stage_plan(topic, settings, folder)
    set_state(phase="approve", plan=plan, stage=1)
    say("Plan ready. Review it before approving.")


def job_research(plan):
    settings, problem = read_settings()
    if problem:
        raise SystemExit(problem)
    folder = Path(STATE["folder"])
    plan = stages.validate_plan(plan, STATE["topic"])
    (folder / "1_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "1_plan_approved.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    say("Plan approved by the researcher.")
    # The whole cycle is shared with the terminal version (stages.run_research)
    stages.run_research(plan, settings, folder, say=say, on_stage=enter_step)
    with LOCK:
        if 10 not in STATE["completed_steps"]:
            STATE["completed_steps"].append(10)
    set_state(phase="done", stage=len(pipeline.STEPS))
    record_event("done", len(pipeline.STEPS), "Manuscript and audit files are available; researcher verification is still required")
    say("Complete.")


def run_checks():
    """Test every connection quickly, so problems show up before research starts."""
    settings, problem = read_settings()
    if problem:
        return [{"name": "Settings file", "ok": False, "note": problem}]
    if settings["DEMO_MODE"]:
        return [{"name": "Demo mode", "ok": True,
                 "note": "Demo mode uses fictional sample data without network requests. Turn it off to test live APIs."}]
    results = []
    try:
        reply = llm.ask("Reply with the single word: OK", settings, stage="check")
        results.append({"name": "AI model (OpenRouter)", "ok": True, "note": f"Response: {reply.strip()[:40]}"})
    except SystemExit as stop:
        results.append({"name": "AI model (OpenRouter)", "ok": False, "note": str(stop).strip()})
    found = tools.search_papers("public policy", settings, how_many=2)
    results.append({"name": "Literature search (OpenAlex)", "ok": bool(found),
                    "note": f"{len(found)} articles found" if found else "No results received. Check the service connection and OpenAlex credentials."})
    if found:
        ok, note = tools.verify_doi(found[0]["doi"], found[0]["title"], settings)
        results.append({"name": "Metadata check (Crossref)", "ok": ok, "note": note})
    set_state()
    return results


def read_results():
    folder = Path(STATE["folder"]) if STATE["folder"] else None
    if not folder or not folder.exists():
        return {}
    def latest(pattern):
        files = sorted(folder.glob(pattern), key=lambda p: int("".join(c for c in p.stem.split("_v")[-1] if c.isdigit()) or 0))
        return files[-1] if files else None
    matrix = []
    if (folder / "4_literature_matrix.csv").exists():
        with open(folder / "4_literature_matrix.csv", encoding="utf-8-sig") as f:
            matrix = list(csv.DictReader(f))
    draft = folder / "7_final_draft.md" if (folder / "7_final_draft.md").exists() else latest("5_draft_v*.md")
    review = folder / "7_final_review.json" if (folder / "7_final_review.json").exists() else latest("6_review_v*.json")
    verified_file = folder / '8_human_verification.json'
    verification = json.loads(verified_file.read_text(encoding='utf-8')) if verified_file.exists() else None
    redteam_file = folder / '7_redteam_review.json'
    section_file = folder / '8_section_status.json'
    paper_file = folder / '9_paper_review.json'
    return {
        "source_access": json.loads((folder / "4_source_manifest.json").read_text(encoding="utf-8")) if (folder / "4_source_manifest.json").exists() else [],
        "fulltext_reading": json.loads((folder / "4_fulltext_reading.json").read_text(encoding="utf-8")) if (folder / "4_fulltext_reading.json").exists() else [],
        "editorial": json.loads((folder / "9_editorial_report.json").read_text(encoding="utf-8")) if (folder / "9_editorial_report.json").exists() else None,
        "paper_review": json.loads(paper_file.read_text(encoding='utf-8')) if paper_file.exists() else None,
        "verification": verification,
        "verification_progress": manuscript.verified_count(verification) if verification else None,
        "redteam": json.loads(redteam_file.read_text(encoding='utf-8')) if redteam_file.exists() else None,
        "section_status": json.loads(section_file.read_text(encoding='utf-8')) if section_file.exists() else None,
        "folder_name": folder.name,
        "matrix": matrix,
        "draft": draft.read_text(encoding="utf-8") if draft else "",
        "draft_file": draft.name if draft else "",
        "review": json.loads(review.read_text(encoding="utf-8")) if review else None,
        "evidence": json.loads((folder / "7_final_evidence_audit.json").read_text(encoding="utf-8"))
                    if (folder / "7_final_evidence_audit.json").exists() else None,
        "files": sorted(p.name for p in folder.iterdir()),
    }


# ---------------------------------------------------------------------------
# The web server: maps page requests to the functions above
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the black window quiet
        pass

    def send(self, data, status=200, kind="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind + ("; charset=utf-8" if "text" in kind or "json" in kind else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 <= length <= 128_000:
            raise ValueError("Invalid request size (maximum 128 KB).")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("The request body must be a JSON object.")
        return data

    def safe_host(self):
        return self.headers.get('Host', '') in (f'localhost:{PORT}', f'127.0.0.1:{PORT}')

    def same_origin(self):
        origin = self.headers.get('Origin', '')
        return not origin or origin in (f'http://localhost:{PORT}', f'http://127.0.0.1:{PORT}')

    def do_GET(self):
        if not self.safe_host():
            return self.send({'error': 'Host not allowed.'}, 403)
        if self.path == '/api/library':
            return self.send({'pdfs': sources.list_pdfs(sources.library_path())})
        if self.path in ("/", "/index.html"):
            return self.send((HERE / "ui.html").read_bytes(), kind="text/html")
        if self.path == "/api/status":
            with LOCK:
                status = dict(STATE, log=STATE["log"][-200:], events=STATE["events"][-80:],
                              completed_steps=list(STATE["completed_steps"]),
                              usage_by_stage={k: dict(v) for k, v in STATE["usage_by_stage"].items()})
            settings, _ = read_settings()
            status["pipeline"] = pipeline.describe(settings or {"DEMO_MODE": True})
            return self.send(status)
        if self.path == "/api/settings":
            return self.send(public_settings())
        if self.path == "/api/results":
            return self.send(read_results())
        if self.path.startswith("/files/"):
            parts = self.path.split("/")
            if len(parts) == 4:
                run, name = unquote(parts[2]), unquote(parts[3])
                allowed_run = re.fullmatch(r"\d{8}_\d{6}(?:_\d{6})?", run)
                allowed_file = re.fullmatch(r"[1-9]_[a-z0-9_]+\.(?:md|csv|json|docx|bib)|9_research_bundle\.zip|log\.txt", name)
                current = Path(STATE["folder"]).name if STATE["folder"] else None
                if allowed_run and allowed_file and run == current:
                    target = PROJECTS / run / name
                    if name == "9_research_bundle.zip":
                        return self.send(editorial.research_bundle(PROJECTS / run), kind="application/zip")
                    if target.is_file() and target.resolve().parent == (PROJECTS / run).resolve():
                        body = target.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return self.wfile.write(body)
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        if not self.safe_host():
            return self.send({'error': 'Host not allowed.'}, 403)
        # Malicious sites must not be able to submit cross-origin forms to a
        # loopback service holding users' API credentials.
        if not self.same_origin():
            return self.send({"error": "Origin not allowed."}, 403)
        if self.path == '/api/upload-pdf':
            if STATE['phase'] in ('planning', 'running'):
                return self.send({'error': 'Upload PDFs before starting the research run.'}, 409)
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/pdf':
                return self.send({'error': 'Content-Type must be application/pdf.'}, 415)
            try:
                length = int(self.headers.get('Content-Length') or 0)
                if not 20 <= length <= sources.MAX_PDF_BYTES:
                    raise ValueError('Maximum file size: 12 MB per PDF.')
                doi = self.headers.get('X-Paper-DOI', '')
                name = unquote(self.headers.get('X-Filename', 'artikel.pdf')[:300])
                result = sources.import_pdf(sources.library_path(), doi, name, self.rfile.read(length))
                return self.send({'ok': True, 'pdf': result})
            except (ValueError, RuntimeError) as exc:
                return self.send({'error': str(exc)[:250]}, 400)
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.send({"error": "Content-Type must be application/json."}, 415)
        try:
            data = self.body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send({"error": str(exc)[:200]}, 400)
        if self.path == '/api/verification':
            if STATE['phase'] != 'done':
                return self.send({'error': 'The checklist is available after the run finishes.'}, 409)
            folder = Path(STATE['folder'])
            csv_path = folder / '4_literature_matrix.csv'
            if not csv_path.exists():
                return self.send({'error': 'The source matrix is not available yet.'}, 409)
            with csv_path.open(encoding='utf-8-sig', newline='') as stream:
                matrix = list(csv.DictReader(stream))
            try:
                record = manuscript.normalize_verification(data, matrix)
            except ValueError as exc:
                return self.send({'error': str(exc)}, 400)
            stages.save_json(folder, '8_human_verification.json', record)
            progress = manuscript.verified_count(record)
            # The final paper exists only after both the AI gate and the researcher checklist pass.
            released = progress['all_checked'] and paper.release_final(folder, say=say)
            if released:
                old_report = folder / '9_editorial_report.json'
                language = json.loads(old_report.read_text(encoding='utf-8')).get('language', 'English') if old_report.exists() else 'English'
                editorial.save_outputs(folder, matrix, language)
            return self.send({'ok': True, 'progress': progress, 'released': bool(released)})
        if self.path == "/api/settings":
            if STATE["phase"] in ("planning", "running"):
                return self.send({"error": "Settings cannot be changed during a research run."}, 409)
            try:
                save_settings(data)
            except ValueError as exc:
                return self.send({"error": str(exc)[:250]}, 400)
            return self.send(dict(public_settings(), ok=True))
        if self.path == "/api/models":
            # Public model catalogue; contacted only when the researcher asks for it.
            try:
                return self.send({"models": llm.list_models(data.get("free_only", True))})
            except RuntimeError as exc:
                return self.send({"error": str(exc)[:250]}, 502)
        if self.path == "/api/check":
            if STATE["phase"] in ("planning", "running"):
                return self.send({"error": "A research run is already active."}, 409)
            return self.send(run_checks())
        if self.path == "/api/plan":
            topic = data.get("topic", "").strip()
            if not topic:
                return self.send({"error": "Enter a research topic."}, 400)
            if STATE["phase"] not in ("idle", "failed", "done"):
                return self.send({"error": "Finish or reset the current plan before starting another."}, 409)
            if isinstance(data.get("research"), dict):
                try:
                    save_settings(data["research"], allowed=RESEARCH_FIELDS)
                except ValueError as exc:
                    return self.send({"error": str(exc)[:250]}, 400)
            llm.REQUESTS_USED[0] = 0
            set_state(phase="planning", stage=1, log=[], plan=None, topic=topic, folder="", error="",
                      completed_steps=[], events=[], usage_by_stage={}, active_model="", stage_started="")
            run_in_background(lambda: job_plan(topic))
            return self.send({"ok": True})
        if self.path == "/api/approve":
            if STATE["phase"] != "approve" or not data.get("approved_scope"):
                return self.send({"error": "Review and approve the scope first."}, 409)
            try:
                plan = stages.validate_plan(data.get("plan") or STATE["plan"], STATE["topic"])
            except ValueError as exc:
                return self.send({"error": str(exc)}, 400)
            set_state(phase="running", plan=plan)
            record_event("approval", 1, "Scope approved by the researcher")
            run_in_background(lambda: job_research(plan))
            return self.send({"ok": True})
        if self.path == "/api/reset":
            if STATE["phase"] in ("planning", "running"):
                return self.send({"error": "Cannot reset an active research run."}, 409)
            set_state(phase="idle", stage=0, log=[], plan=None, topic="", folder="", error="",
                      completed_steps=[], events=[], usage_by_stage={}, active_model="", stage_started="")
            return self.send({"ok": True})
        if self.path == "/api/open-folder" and STATE["folder"] and hasattr(os, "startfile"):
            os.startfile(STATE["folder"])  # Windows: opens the results folder
            return self.send({"ok": True})
        self.send({"error": "not found"}, 404)


def main():
    ensure_env()
    PROJECTS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"\n  Papermuller is running at {url}")
    print("  Keep this terminal open while using the app. Press Ctrl+C to stop.\n")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
