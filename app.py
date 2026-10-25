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
from i18n import tr, set_language

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
PROJECTS = HERE / "projects"
PORT = 8765

# Everything the page needs to know about the current job lives here.
STATE = {"phase": "idle", "stage": 0, "log": [], "plan": None, "topic": "",
         "folder": "", "error": "", "requests": 0}
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
        settings = harness.load_settings()
        set_language(settings["UI_LANGUAGE"])
        return settings, ""
    except SystemExit as stop:
        return None, str(stop)


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
        sys.stdout = PageLog(Path(STATE["folder"]) if STATE["folder"] else None)
        try:
            job()
        except SystemExit as stop:
            set_state(phase="failed", error=str(stop).strip() or tr("stopped"))
        except Exception as error:  # unexpected problem: show it instead of crashing
            set_state(phase="failed", error=f"{type(error).__name__}: {error}")
        finally:
            sys.stdout = old
            set_state()
    threading.Thread(target=wrapper, daemon=True).start()


# ---------------------------------------------------------------------------
# The jobs
# ---------------------------------------------------------------------------
def job_plan(topic):
    settings, problem = read_settings()
    if problem:
        raise SystemExit(problem)
    folder = PROJECTS / datetime.now().strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True)
    set_state(folder=str(folder))
    sys.stdout.folder = folder
    say(tr("topic", t=topic))
    say(tr("mode_demo" if settings["DEMO_MODE"] else "mode_real"))
    say(tr("plan_start"))
    plan = stages.stage_plan(topic, settings, folder)
    set_state(phase="approve", plan=plan, stage=1)
    say(tr("plan_ready"))


def job_research(plan):
    settings, problem = read_settings()
    if problem:
        raise SystemExit(problem)
    folder = Path(STATE["folder"])
    (folder / "1_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    say(tr("approved"))
    # The whole cycle is shared with the terminal version (stages.run_research)
    stages.run_research(plan, settings, folder, say=say, on_stage=lambda n: set_state(stage=n))
    set_state(phase="done", stage=7)
    say(tr("done"))


def run_checks():
    """Test every connection quickly, so problems show up before research starts."""
    settings, problem = read_settings()
    if problem:
        return [{"name": tr("check_settings"), "ok": False, "note": problem}]
    if settings["DEMO_MODE"]:
        return [{"name": tr("check_demo"), "ok": True, "note": tr("check_demo_note")}]
    results = []
    try:
        reply = llm.ask("Reply with the single word: OK", settings, stage="check")
        results.append({"name": tr("check_ai"), "ok": True, "note": tr("check_ai_reply", r=reply.strip()[:40])})
    except SystemExit as stop:
        results.append({"name": tr("check_ai"), "ok": False, "note": str(stop).strip()})
    found = tools.search_papers("public policy", settings, how_many=2)
    results.append({"name": tr("check_oa"), "ok": bool(found),
                    "note": tr("check_oa_ok", n=len(found)) if found else tr("check_oa_bad")})
    if found:
        ok, note = tools.verify_doi(found[0]["doi"], found[0]["title"], settings)
        results.append({"name": tr("check_cr"), "ok": ok, "note": note})
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
    return {
        "folder_name": folder.name,
        "matrix": matrix,
        "draft": draft.read_text(encoding="utf-8") if draft else "",
        "draft_file": draft.name if draft else "",
        "review": json.loads(review.read_text(encoding="utf-8")) if review else None,
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
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.send((HERE / "ui.html").read_bytes(), kind="text/html")
        if self.path == "/api/status":
            with LOCK:
                return self.send(dict(STATE, log=STATE["log"][-200:]))
        if self.path == "/api/settings":
            settings, problem = read_settings()
            raw = {}
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    raw[k.strip()] = v.strip()
            return self.send({
                "demo": raw.get("DEMO_MODE", "true").lower() == "true",
                "has_openrouter_key": raw.get("OPENROUTER_API_KEY", "").startswith("sk-or-"),
                "has_openalex_key": bool(raw.get("OPENALEX_API_KEY")),
                "model": raw.get("MODEL", ""), "language": raw.get("LANGUAGE", "English"),
                "email": raw.get("EMAIL", ""), "problem": problem,
                "target": raw.get("TARGET_SCORE", "8"),
                "ui_language": raw.get("UI_LANGUAGE", ""),
            })
        if self.path == "/api/results":
            return self.send(read_results())
        if self.path.startswith("/files/"):  # download a result file
            _, _, run, name = self.path.split("/", 3)
            target = (PROJECTS / unquote(run) / unquote(name)).resolve()
            if PROJECTS.resolve() in target.parents and target.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
                self.end_headers()
                return self.wfile.write(target.read_bytes())
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        data = self.body()
        if self.path == "/api/settings":
            updates = {"DEMO_MODE": "true" if data.get("demo") else "false",
                       "MODEL": data.get("model", "").strip(),
                       "LANGUAGE": data.get("language", "English"),
                       "EMAIL": data.get("email", "").strip(),
                       "TARGET_SCORE": str(data.get("target", "8"))}
            # Keys are only replaced when the user typed a new one
            if data.get("openrouter_key", "").strip():
                updates["OPENROUTER_API_KEY"] = data["openrouter_key"].strip()
            if data.get("openalex_key", "").strip():
                updates["OPENALEX_API_KEY"] = data["openalex_key"].strip()
            update_env(updates)
            return self.send({"ok": True})
        if self.path == "/api/ui-language":  # the page's language switcher
            code = data.get("lang", "en")
            update_env({"UI_LANGUAGE": code})
            set_language(code)
            return self.send({"ok": True})
        if self.path == "/api/check":
            return self.send(run_checks())
        if self.path == "/api/plan":
            topic = data.get("topic", "").strip()
            if not topic:
                return self.send({"error": tr("no_topic")}, 400)
            if STATE["phase"] in ("planning", "running"):
                return self.send({"error": tr("busy")}, 409)
            llm.REQUESTS_USED[0] = 0
            set_state(phase="planning", stage=1, log=[], plan=None, topic=topic, folder="", error="")
            run_in_background(lambda: job_plan(topic))
            return self.send({"ok": True})
        if self.path == "/api/approve":
            plan = data.get("plan") or STATE["plan"]
            set_state(phase="running", plan=plan, stage=2)
            run_in_background(lambda: job_research(plan))
            return self.send({"ok": True})
        if self.path == "/api/reset":
            set_state(phase="idle", stage=0, log=[], plan=None, topic="", folder="", error="")
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
    print("  Keep this window open while you use it. Close it to stop.\n")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
