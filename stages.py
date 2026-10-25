"""
stages.py  -  THE "WORKERS"  (version 2, optimised)
===================================================
Each function below is one stage of the research cycle. Every stage follows
the same simple pattern: read what came before, do one job, save a file,
hand the result to the next stage.

What changed in version 2, and why:
  SEARCH   takes the most RELEVANT papers from every keyword in turn,
           instead of only the most-cited ones (which are often off-topic).
  SCREEN   new: the AI reads all titles/abstracts at once and drops papers
           that do not help answer the research questions.
  MATRIX   summarises 4 papers per request (saves free quota) and now also
           records each study's LIMITATION, which makes the synthesis richer.
  OUTLINE  new: the AI plans the themes BEFORE writing, so the review is
           organised by ideas, not paper by paper.
  DRAFT    later rounds REVISE the previous draft using the reviewer's
           concrete fixes, instead of starting from zero.
  REVIEW   scores 5 named criteria with a clear scale. The final score is
           computed by code (the average), so the AI cannot just "say 8".
  BEST     the best-scoring draft is kept, even if a later round is worse,
           and a reference list is added to it.

The AI instructions ("prompts") are plain English, so you can edit them.
"""

import csv
import json
import re

from llm import ask, ask_for_json
from tools import search_papers, verify_doi
from i18n import tr

CRITERIA = {
    "synthesis": "compares and connects studies instead of summarising them one by one",
    "research_gap": "states a specific gap that follows logically from the evidence",
    "coverage": "addresses every research question",
    "evidence_use": "every claim is supported by a citation and no finding is overstated",
    "clarity": "clear structure, smooth flow, academic tone, appropriate length",
}


# ---------------------------------------------------------------------------
# Small file helpers
# ---------------------------------------------------------------------------
def save_text(folder, name, text):
    (folder / name).write_text(text, encoding="utf-8")


def save_json(folder, name, data):
    save_text(folder, name, json.dumps(data, indent=2, ensure_ascii=False))


def save_csv(folder, name, rows):
    if not rows:
        return
    with open(folder / name, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig opens nicely in Excel
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def with_model(settings, model):
    """A copy of the settings that uses another model (e.g. for the reviewer)."""
    if not model:
        return settings
    copy = dict(settings)
    copy["MODEL"] = model
    return copy


# ---------------------------------------------------------------------------
# STAGE 1  -  PLAN
# ---------------------------------------------------------------------------
def stage_plan(topic, settings, folder):
    prompt = f"""
Topic: "{topic}"

Act as a research methodologist. Produce:
- "title": a working title for a journal article
- "research_questions": 2 or 3 clear, answerable research questions
- "keywords": 4 to 6 English search keywords for academic databases.
   Mix broad and specific terms; each should be 2 to 4 words.
- "scope_note": one sentence describing what is in and out of scope

Return JSON with exactly those four keys.
"""
    plan = ask_for_json(prompt, settings, stage="plan")
    save_json(folder, "1_plan.json", plan)
    return plan


# ---------------------------------------------------------------------------
# STAGE 2  -  SEARCH (relevance-balanced)
# ---------------------------------------------------------------------------
def stage_search(plan, settings, folder):
    per_keyword = []
    for keyword in plan["keywords"]:
        print(tr("searching", kw=keyword))
        per_keyword.append(search_papers(keyword, settings, how_many=15))

    # Take result #1 of every keyword, then #2 of every keyword, and so on.
    # OpenAlex already orders by relevance, so this keeps the best of each keyword.
    found = {}
    for rank in range(15):
        for results in per_keyword:
            if rank < len(results):
                paper = results[rank]
                if paper["doi"] and paper["doi"] not in found:
                    found[paper["doi"]] = paper

    papers = list(found.values())[: settings["CANDIDATES"]]
    for number, paper in enumerate(papers, start=1):
        paper["id"] = f"P{number}"
    save_csv(folder, "2_papers_found.csv", papers)
    return papers


# ---------------------------------------------------------------------------
# STAGE 3a  -  VERIFY every paper is real (code + Crossref, no AI)
# ---------------------------------------------------------------------------
def stage_verify(papers, settings, folder):
    verified = []
    for paper in papers:
        ok, reason = verify_doi(paper["doi"], paper["title"], settings)
        paper["verified"] = "yes" if ok else "no"
        paper["check_note"] = reason
        print(f"   {paper['id']}: {'OK ' if ok else 'XX '} {reason}")
        if ok and paper["abstract"]:
            verified.append(paper)
    save_csv(folder, "3_verification_report.csv", papers)
    return verified


# ---------------------------------------------------------------------------
# STAGE 3b  -  SCREEN for relevance (one AI request for all papers)
# ---------------------------------------------------------------------------
def stage_screen(verified, plan, settings, folder):
    listing = "\n".join(f"[{p['id']}] {p['title']} ({p['year']}). {p['abstract'][:350]}" for p in verified)
    prompt = f"""
Research questions: {plan['research_questions']}
Scope: {plan.get('scope_note', '')}

Below are candidate papers. Decide which ones are genuinely useful for answering
the research questions. Prefer empirical studies and strong reviews. Exclude papers
that only share a keyword but are about a different subject.

{listing}

Return JSON: {{"include": ["P1", ...], "excluded": {{"P7": "short reason", ...}}}}
Include at most {settings['MAX_PAPERS']} papers, best first.
"""
    decision = ask_for_json(prompt, settings, stage="screen")
    by_id = {p["id"]: p for p in verified}
    chosen = [by_id[i] for i in decision.get("include", []) if i in by_id][: settings["MAX_PAPERS"]]
    save_json(folder, "3_screening.json", decision)
    print(tr("chosen", c=len(chosen), n=len(verified)))
    return chosen


# ---------------------------------------------------------------------------
# STAGE 4  -  MATRIX (4 papers per request)
# ---------------------------------------------------------------------------
def stage_matrix(papers, plan, settings, folder):
    rows = []
    for start in range(0, len(papers), 4):
        batch = papers[start:start + 4]
        listing = "\n\n".join(
            f"Paper {p['id']}: \"{p['title']}\" ({p['year']})\nAbstract: {p['abstract'][:2000]}" for p in batch)
        prompt = f"""
Research questions: {plan['research_questions']}

{listing}

For EACH paper, using ONLY its abstract (no outside knowledge), extract:
"id", "method" (design, data, sample or setting), "main_finding",
"limitation" (a weakness stated or clearly implied; else "not stated"),
"relevance" (which research question it helps and how).
Keep each value under 40 words.

Return JSON: {{"rows": [{{"id": "...", "method": "...", "main_finding": "...", "limitation": "...", "relevance": "..."}}]}}
"""
        answer = ask_for_json(prompt, settings, stage="matrix")
        found = {r.get("id"): r for r in answer.get("rows", [])}
        for p in batch:
            r = found.get(p["id"], {})
            rows.append({
                "id": p["id"], "authors": p["authors"], "year": p["year"], "title": p["title"],
                "doi": p["doi"],
                "method": r.get("method", "not stated"),
                "main_finding": r.get("main_finding", "not stated"),
                "limitation": r.get("limitation", "not stated"),
                "relevance": r.get("relevance", ""),
            })
        print(tr("summarised", ids=", ".join(p["id"] for p in batch)))
    save_csv(folder, "4_literature_matrix.csv", rows)
    return rows


def evidence_text(matrix):
    return "\n".join(
        f"[{r['id']}] {r['authors']} ({r['year']}). {r['title']}. Method: {r['method']}. "
        f"Finding: {r['main_finding']}. Limitation: {r['limitation']}"
        for r in matrix)


# ---------------------------------------------------------------------------
# STAGE 5a  -  OUTLINE (plan the argument before writing)
# ---------------------------------------------------------------------------
def stage_outline(matrix, plan, settings, folder):
    prompt = f"""
Research questions: {plan['research_questions']}

EVIDENCE:
{evidence_text(matrix)}

Plan a literature review organised by THEMES, not by paper. Return JSON:
{{"themes": [{{"name": "...", "papers": ["P1", "P3"], "point": "what these studies show together, including where they agree or disagree"}}],
  "gap": "the specific research gap that follows from the themes, linked to the research questions"}}
Use 3 or 4 themes. Every paper should appear in at least one theme.
"""
    outline = ask_for_json(prompt, settings, stage="outline")
    save_json(folder, "5_outline.json", outline)
    return outline


# ---------------------------------------------------------------------------
# STAGE 5b  -  DRAFT (first write, later rounds revise)
# ---------------------------------------------------------------------------
def stage_draft(matrix, plan, outline, settings, folder, attempt=1, previous="", fixes=""):
    rules = f"""
STRICT RULES:
1. Use ONLY the evidence list. Never cite anything else.
2. Cite with the paper ID in square brackets, e.g. [P2] or [P1; P4].
3. Synthesise: compare methods and findings, point out agreements, contradictions and
   limitations. Never write one paragraph per paper.
4. Every paragraph must contain at least one citation. Do not invent numbers or findings.
5. Length 600 to 900 words. Language: {settings['LANGUAGE']}. Academic, clear, natural tone.
6. Use a short heading for each theme, and end with a "Research gap" paragraph.
"""
    if previous:
        prompt = f"""
You are revising your literature review for the article "{plan['title']}".
Research questions: {plan['research_questions']}

A peer reviewer asked for these fixes. Address EVERY one of them, keep what already works:
{fixes}
{rules}
EVIDENCE:
{evidence_text(matrix)}

CURRENT DRAFT:
{previous}

Return only the full revised draft.
"""
    else:
        prompt = f"""
Write the literature review section for the article "{plan['title']}".
Research questions: {plan['research_questions']}

Follow this outline (themes, papers per theme, and the gap):
{json.dumps(outline, ensure_ascii=False)}
{rules}
EVIDENCE:
{evidence_text(matrix)}
"""
    draft = ask(prompt, settings, stage="draft")
    save_text(folder, f"5_draft_v{attempt}.md", draft)
    return draft


def check_citations(draft, matrix):
    """QUALITY GATE done by plain code: every [P#] must be a verified, screened paper."""
    allowed = {row["id"] for row in matrix}
    used = set(re.findall(r"P\d+", " ".join(re.findall(r"\[([^\]]+)\]", draft))))
    return sorted(used - allowed), sorted(used)


# ---------------------------------------------------------------------------
# STAGE 6  -  REVIEW with a rubric (score computed by code)
# ---------------------------------------------------------------------------
def stage_review(draft, plan, settings, folder, attempt=1):
    rubric = "\n".join(f'- "{k}": {v}' for k, v in CRITERIA.items())
    prompt = f"""
You are a strict, fair peer reviewer for a reputable journal. You did NOT write this draft.
Research questions: {plan['research_questions']}

Score each criterion from 1 to 10:
{rubric}

Scale: 9-10 = excellent, publishable as is; 8 = strong, minor edits only;
6-7 = acceptable but clear weaknesses; 4-5 = weak; 1-3 = unusable. Be honest, do not inflate.

DRAFT:
{draft}

Return JSON:
{{"scores": {{"synthesis": 0, "research_gap": 0, "coverage": 0, "evidence_use": 0, "clarity": 0}},
  "strengths": ["up to 3 short points"],
  "fixes": ["up to 5 concrete, actionable instructions, e.g. 'Compare the methods of P2 and P5 in the second section'"]}}
"""
    review = ask_for_json(prompt, with_model(settings, settings.get("REVIEW_MODEL")), stage="review")
    scores = {k: max(1, min(10, int(float(review.get("scores", {}).get(k, 5))))) for k in CRITERIA}
    review["scores"] = scores
    review["score"] = round(sum(scores.values()) / len(scores), 1)  # computed by code, not by the AI
    review["verdict"] = "accept" if review["score"] >= settings["TARGET_SCORE"] else "revise"
    review.setdefault("fixes", review.get("problems", []))
    save_json(folder, f"6_review_v{attempt}.json", review)
    return review


def references(matrix):
    lines = [f"[{r['id']}] {r['authors']} ({r['year']}). {r['title']}. https://doi.org/{r['doi']}" for r in matrix]
    return "\n\n## References\n\n" + "\n\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# THE WHOLE CYCLE after the plan is approved (used by harness.py and app.py)
# ---------------------------------------------------------------------------
def run_research(plan, settings, folder, say=print, on_stage=lambda n: None):
    on_stage(2)
    say(tr("search_start"))
    papers = stage_search(plan, settings, folder)
    say(tr("candidates", n=len(papers)))

    on_stage(3)
    say(tr("verify_start"))
    verified = stage_verify(papers, settings, folder)
    say(tr("verified", v=len(verified), n=len(papers)))
    chosen = stage_screen(verified, plan, settings, folder) if verified else []
    if len(chosen) < settings["MIN_VERIFIED"]:
        raise SystemExit(tr("too_few", m=settings["MIN_VERIFIED"]))

    on_stage(4)
    say(tr("matrix_start"))
    matrix = stage_matrix(chosen, plan, settings, folder)

    on_stage(5)
    say(tr("outline_start"))
    outline = stage_outline(matrix, plan, settings, folder)

    best, previous, fixes = None, "", ""
    for attempt in range(1, settings["REVISION_ROUNDS"] + 2):
        on_stage(5)
        say(tr("draft_write" if attempt == 1 else "draft_revise", r=attempt))
        draft = stage_draft(matrix, plan, outline, settings, folder, attempt, previous, fixes)

        fake_ids, used = check_citations(draft, matrix)
        if fake_ids:
            say(tr("cite_fail", ids=fake_ids))
            previous, fixes = draft, f"- Remove or replace the citations {fake_ids}; they are NOT in the evidence list."
            continue
        coverage = len(used) / len(matrix)
        say(tr("cite_ok", u=len(used), n=len(matrix)))

        on_stage(6)
        say(tr("review_start", r=attempt))
        review = stage_review(draft, plan, settings, folder, attempt)
        detail = ", ".join(f"{k} {v}" for k, v in review["scores"].items())
        say(tr("review_score", s=review["score"], t=settings["TARGET_SCORE"], detail=detail))

        if best is None or review["score"] > best[0]:
            best = (review["score"], attempt, draft, review)
        if review["verdict"] == "accept":
            say(tr("target_reached"))
            break
        previous = draft
        fixes = "\n".join(f"- {f}" for f in review.get("fixes", []))
        if coverage < 0.6:
            fixes += "\n- Use more of the evidence: several listed papers are never cited."
    else:
        if best:
            say(tr("limit_best", r=best[1], s=best[0]))

    if not best:
        raise SystemExit(tr("no_draft"))
    score, attempt, draft, review = best
    review["from_round"] = attempt
    save_text(folder, "7_final_draft.md", draft + references(matrix))
    save_json(folder, "7_final_review.json", review)
    say(tr("final_saved", r=attempt, s=score))
    return review
