"""
harness.py  -  THE "MANAGER"  (this is the file you run)
=========================================================
This is the orchestrator. It does not do research itself.
It decides the ORDER of work, checks the QUALITY GATES, asks YOU for
approval at the important moment, and keeps a LOG of everything.

How to run (in a terminal, inside this folder):
    python harness.py "your research topic here"

The flow:
    PLAN -> [you approve] -> SEARCH -> VERIFY (gate) -> SCREEN -> MATRIX
         -> OUTLINE -> DRAFT -> CITATION CHECK (gate) -> REVIEW (rubric, may loop)
         -> BEST DRAFT + REFERENCES
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import stages


# ---------------------------------------------------------------------------
# 1. Read your settings from the .env file
# ---------------------------------------------------------------------------
def load_settings():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        sys.exit("No .env file found. Copy 'env.example' to '.env' first (see README).")

    raw = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            raw[key.strip()] = value.strip().strip('"')

    settings = {
        "DEMO_MODE": raw.get("DEMO_MODE", "true").lower() == "true",
        "OPENROUTER_API_KEY": raw.get("OPENROUTER_API_KEY", ""),
        "MODEL": raw.get("MODEL", "openrouter/auto"),
        "LANGUAGE": raw.get("LANGUAGE", "English"),
        "FROM_YEAR": int(raw.get("FROM_YEAR", "2015")),
        "MAX_PAPERS": int(raw.get("MAX_PAPERS", "12")),
        "MIN_VERIFIED": int(raw.get("MIN_VERIFIED", "5")),
        # The reviewer's average score a draft must reach (1-10)
        "TARGET_SCORE": float(raw.get("TARGET_SCORE", "8")),
        # Extra revision rounds after the first draft
        "REVISION_ROUNDS": int(raw.get("REVISION_ROUNDS", "3")),
        # How many candidate papers to verify before screening
        "CANDIDATES": int(raw.get("CANDIDATES", "30")),
        # Optional different model for the reviewer (a second opinion)
        "REVIEW_MODEL": raw.get("REVIEW_MODEL", ""),
        "WRITER_MODEL": raw.get("WRITER_MODEL", ""),
        "EVIDENCE_MODEL": raw.get("EVIDENCE_MODEL", ""),
        "VERIFIER_MODEL": raw.get("VERIFIER_MODEL", ""),
        "EMAIL": raw.get("EMAIL", ""),
        "OPENALEX_API_KEY": raw.get("OPENALEX_API_KEY", ""),
        # Servers (providers) to skip, comma-separated, e.g. Nvidia
        "IGNORE_PROVIDERS": raw.get("IGNORE_PROVIDERS", ""),
        "PDF_LIBRARY": str(Path(__file__).parent / 'library'),
    }
    if not settings["DEMO_MODE"] and not settings["OPENROUTER_API_KEY"].startswith("sk-or-"):
        sys.exit("Real mode needs a valid OPENROUTER_API_KEY in .env (it starts with sk-or-).")
    if (settings["CANDIDATES"] < 1 or settings["MAX_PAPERS"] < 1 or
        settings["MIN_VERIFIED"] < 1 or
        settings["MIN_VERIFIED"] > settings["MAX_PAPERS"] or
        settings["REVISION_ROUNDS"] < 0 or settings["REVISION_ROUNDS"] > 10 or
        not 1 <= settings["TARGET_SCORE"] <= 10):
        sys.exit("Pengaturan tidak masuk akal: periksa batas artikel, putaran revisi, dan target skor.")
    return settings


# ---------------------------------------------------------------------------
# 2. A tiny logger: prints to screen AND writes to log.txt
# ---------------------------------------------------------------------------
class Log:
    def __init__(self, folder):
        self.file = folder / "log.txt"

    def say(self, message):
        line = f"[{datetime.now():%H:%M:%S}] {message}"
        print(line)
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def banner(text):
    print("\n" + "=" * 60 + f"\n  {text}\n" + "=" * 60)


# ---------------------------------------------------------------------------
# 3. The main cycle
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python harness.py "your research topic"')
    topic = sys.argv[1]
    settings = load_settings()

    # Every run gets its own folder, so nothing is ever overwritten
    folder = Path(__file__).parent / "projects" / datetime.now().strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True)
    log = Log(folder)
    log.say(f"Topic: {topic}")
    log.say(f"Mode: {'DEMO (free, sample data)' if settings['DEMO_MODE'] else 'REAL'} | Model: {settings['MODEL']}")

    # ---- STAGE 1: PLAN ----------------------------------------------------
    banner("STAGE 1/6  PLAN")
    plan = stages.stage_plan(topic, settings, folder)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    # ---- HUMAN CHECKPOINT -------------------------------------------------
    # The most important decision (what to research) stays with you.
    answer = input("\nApprove this plan? [y = continue / n = stop]: ").strip().lower()
    if answer != "y":
        log.say("Stopped by user at plan approval. Edit the topic and run again.")
        return
    stages.save_json(folder, "1_plan_approved.json", plan)
    log.say("Plan approved by user. Scope frozen for subsequent stages.")

    # ---- STAGES 2-6: search, verify, screen, matrix, outline, draft, review ----
    # The whole cycle lives in stages.run_research, shared with the web app.
    try:
        review = stages.run_research(plan, settings, folder, say=log.say)
    except SystemExit as stop:
        log.say(f"STOPPED: {stop}")
        return

    banner("DONE")
    log.say(f"All results are in: {folder}")
    print("\nFiles to open:\n  7_final_draft.md         (best draft + references)\n"
          "  4_literature_matrix.csv  (Excel)\n  7_final_review.json      (reviewer scores)\n"
          "  log.txt                  (what happened)")


if __name__ == "__main__":
    main()
