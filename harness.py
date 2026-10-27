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
import writing


# ---------------------------------------------------------------------------
# 1. Read your settings from the .env file
# ---------------------------------------------------------------------------
CURRENT_YEAR = datetime.now().year

# Every model a stage can use. An empty value falls back to the next key in
# the chain, and finally to MODEL. Comma-separated values are fallbacks.
STAGE_MODEL_KEYS = ["PLAN_MODEL", "SCREEN_MODEL", "EVIDENCE_MODEL", "OUTLINE_MODEL",
                    "WRITER_MODEL", "VERIFIER_MODEL", "REVIEW_MODEL", "REDTEAM_MODEL",
                    "PAPER_MODEL", "PAPER_REVIEW_MODEL"]
WORK_TYPES = {"any": "", "article": "article", "review": "review", "article_review": "article|review"}


def parse_settings(raw):
    """Turn raw KEY=value strings into checked settings. Raises ValueError."""
    def number(key, default, low, high, kind=int):
        text = str(raw.get(key, "") or default).strip()
        try:
            value = kind(text)
        except ValueError:
            raise ValueError(f"{key} must be a number.")
        if not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
        return value

    from_year = number("FROM_YEAR", 2015, 1900, CURRENT_YEAR + 1)
    to_year = number("TO_YEAR", CURRENT_YEAR, 1900, CURRENT_YEAR + 1)
    if from_year > to_year:
        raise ValueError("FROM_YEAR cannot be later than TO_YEAR.")
    work_type = str(raw.get("WORK_TYPE", "any") or "any").strip().lower()
    if work_type not in WORK_TYPES:
        raise ValueError("WORK_TYPE must be one of: " + ", ".join(WORK_TYPES) + ".")
    settings = {
        "DEMO_MODE": str(raw.get("DEMO_MODE", "true")).lower() == "true",
        "OPENROUTER_API_KEY": raw.get("OPENROUTER_API_KEY", ""),
        "MODEL": raw.get("MODEL", "") or "openrouter/free",
        "LANGUAGE": writing.validate_language(raw.get("LANGUAGE", "English")),
        # Publication window and document filters for the literature search
        "FROM_YEAR": from_year,
        "TO_YEAR": to_year,
        "WORK_TYPE": work_type,
        "FETCH_FULLTEXT": str(raw.get("FETCH_FULLTEXT", "true")).lower() == "true",
        "REQUIRE_FULLTEXT": str(raw.get("REQUIRE_FULLTEXT", "false")).lower() == "true",
        "OPEN_ACCESS_ONLY": str(raw.get("OPEN_ACCESS_ONLY", "false")).lower() == "true",
        "MIN_CITATIONS": number("MIN_CITATIONS", 0, 0, 100000),
        "MAX_PAPERS": number("MAX_PAPERS", 12, 1, 40),
        "MIN_VERIFIED": number("MIN_VERIFIED", 5, 1, 40),
        # The reviewer's average score a draft must reach (1-10)
        "TARGET_SCORE": number("TARGET_SCORE", 8, 1, 10, float),
        # Extra revision rounds after the first draft
        "REVISION_ROUNDS": number("REVISION_ROUNDS", 3, 0, 10),
        # How many candidate papers to verify before screening
        "CANDIDATES": number("CANDIDATES", 30, 1, 100),
        "EMAIL": raw.get("EMAIL", ""),
        "OPENALEX_API_KEY": raw.get("OPENALEX_API_KEY", ""),
        # Servers (providers) to skip, comma-separated, e.g. Nvidia
        "IGNORE_PROVIDERS": raw.get("IGNORE_PROVIDERS", ""),
        "PDF_LIBRARY": str(Path(__file__).parent / 'library'),
    }
    for key in STAGE_MODEL_KEYS:
        settings[key] = raw.get(key, "")
    if settings["MIN_VERIFIED"] > settings["MAX_PAPERS"]:
        raise ValueError("MIN_VERIFIED cannot be larger than MAX_PAPERS.")
    if not settings["DEMO_MODE"] and not settings["OPENROUTER_API_KEY"].startswith("sk-or-"):
        raise ValueError("Real mode needs a valid OPENROUTER_API_KEY in .env (it starts with sk-or-).")
    return settings


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
    try:
        return parse_settings(raw)
    except ValueError as problem:
        sys.exit(f"Invalid settings: {problem}")


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
