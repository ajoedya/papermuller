"""Stable, honest UI descriptions for the local research pipeline.

Stages report actual transitions; percentage, cost and tokens are intentionally
not fabricated when an upstream provider does not supply them.
"""

STEPS = [{'id': 1,
  'name': 'Research plan',
  'summary': 'Brainstorm topics, define questions and approve the scope',
  'engine': 'Researcher + AI',
  'input': 'Research topic',
  'output': 'Approved research plan',
  'role': 'planner'},
 {'id': 2,
  'name': 'Literature discovery',
  'summary': 'Search OpenAlex for relevant publications',
  'engine': 'OpenAlex',
  'input': 'Search terms and year filter',
  'output': 'Candidate articles',
  'role': 'retriever'},
 {'id': 3,
  'name': 'Metadata & PDFs',
  'summary': 'Match Crossref metadata and locate uploaded PDFs',
  'engine': 'Crossref · PDF parser',
  'input': 'Candidate articles and local PDFs',
  'output': 'Articles with matching metadata',
  'role': 'parser'},
 {'id': 4,
  'name': 'Source selection',
  'summary': 'Select articles relevant to the research questions',
  'engine': 'AI + rules',
  'input': 'Articles with matching metadata',
  'output': 'Selected articles',
  'role': 'screen'},
 {'id': 5,
  'name': 'Evidence extraction',
  'summary': 'Record source quotes and page references',
  'engine': 'Extraction model',
  'input': 'Selected PDF excerpts or abstracts',
  'output': 'Source matrix with provenance',
  'role': 'evidence'},
 {'id': 6,
  'name': 'Literature synthesis',
  'summary': 'Identify themes and gaps in the selected evidence',
  'engine': 'Writing model',
  'input': 'Source matrix',
  'output': 'Thematic outline',
  'role': 'writer'},
 {'id': 7,
  'name': 'Draft writing',
  'summary': 'Write and revise the literature review',
  'engine': 'Writing model',
  'input': 'Outline and evidence',
  'output': 'Draft with source citations',
  'role': 'writer'},
 {'id': 8,
  'name': 'Citation & claim audit',
  'summary': 'Check citation IDs and supporting evidence',
  'engine': 'Audit model + rules',
  'input': 'Draft and source excerpts',
  'output': 'Claim audit report',
  'role': 'verifier'},
 {'id': 9,
  'name': 'Critical review',
  'summary': 'Score the draft and flag methodological concerns',
  'engine': 'Review model',
  'input': 'Draft and evidence audit',
  'output': 'Review findings and revision suggestions',
  'role': 'reviewer'},
 {'id': 10,
  'name': 'Full paper draft',
  'summary': 'Draft title, abstract, introduction, discussion and conclusion',
  'engine': 'Writing model',
  'input': 'Reviewed literature review and author-supplied methods/results',
  'output': 'Complete draft article',
  'role': 'paper_writer'},
 {'id': 11,
  'name': 'Final paper review',
  'summary': 'Review the whole article before it can be released',
  'engine': 'Review model + rules',
  'input': 'Complete draft article',
  'output': 'Release decision and revision requests',
  'role': 'paper_reviewer'},
 {'id': 12,
  'name': 'Export & review',
  'summary': 'Save the paper (.md, .docx), evidence ledger, and checklist',
  'engine': 'Python',
  'input': 'Reviewed paper and audits',
  'output': 'Local files for researcher review',
  'role': 'system'}]

# AI stages and the settings key(s) that pick their model, in fallback order.
# Each entry is shown as an editable model slot on the flowchart.
STAGE_MODEL_SLOTS = {
    1: [{"key": "PLAN_MODEL", "label": "Planner", "chain": ["PLAN_MODEL"]}],
    4: [{"key": "SCREEN_MODEL", "label": "Screener", "chain": ["SCREEN_MODEL"]}],
    5: [{"key": "EVIDENCE_MODEL", "label": "Extractor", "chain": ["EVIDENCE_MODEL"]}],
    6: [{"key": "OUTLINE_MODEL", "label": "Synthesis", "chain": ["OUTLINE_MODEL", "WRITER_MODEL"]}],
    7: [{"key": "WRITER_MODEL", "label": "Writer", "chain": ["WRITER_MODEL"]}],
    8: [{"key": "VERIFIER_MODEL", "label": "Auditor", "chain": ["VERIFIER_MODEL"]}],
    9: [{"key": "REVIEW_MODEL", "label": "Reviewer", "chain": ["REVIEW_MODEL"]},
        {"key": "REDTEAM_MODEL", "label": "Red-team", "chain": ["REDTEAM_MODEL", "REVIEW_MODEL"]}],
    10: [{"key": "PAPER_MODEL", "label": "Paper writer", "chain": ["PAPER_MODEL", "WRITER_MODEL"]}],
    11: [{"key": "PAPER_REVIEW_MODEL", "label": "Paper reviewer", "chain": ["PAPER_REVIEW_MODEL", "REVIEW_MODEL"]}],
}
SERVICES = {2: "OpenAlex API", 3: "Crossref + pypdf", 12: "Local Python"}
ROLE_KEYS = {"planner": "PLAN_MODEL", "screen": "SCREEN_MODEL", "evidence": "EVIDENCE_MODEL",
             "writer": "WRITER_MODEL", "verifier": "VERIFIER_MODEL", "reviewer": "REVIEW_MODEL",
             "paper_writer": "PAPER_MODEL", "paper_reviewer": "PAPER_REVIEW_MODEL"}


def estimate_requests(settings):
    """How many AI requests the research run needs once the plan is approved.

    Gives the fewest and the most, with the parts they are made of. The fewest is a run whose first
    draft and first paper pass review (or that has no revision rounds to spend); the most uses every
    revision round. A request that is repeated after an error counts again, so the real number can
    be higher."""
    fewest_papers = max(1, int(settings.get("MIN_VERIFIED") or 1))
    most_papers = max(fewest_papers, int(settings.get("MAX_PAPERS") or fewest_papers))
    rounds = int(settings.get("REVISION_ROUNDS") or 0) + 1
    batches = lambda n: -(-n // 4)  # evidence is extracted four articles per request
    parts = [
        {"part": "screen", "min": 1, "max": 1},
        {"part": "evidence", "min": batches(fewest_papers), "max": batches(most_papers)},
        {"part": "outline", "min": 1, "max": 1},
        # Per round: draft, claim audit, review. A round that fails the citation check costs only the draft,
        # so with few rounds the fewest can be below 3.
        {"part": "review_rounds", "min": min(3, rounds), "max": 3 * rounds},
        {"part": "redteam", "min": 1, "max": 1},
        {"part": "paper_rounds", "min": 2, "max": 2 * rounds},    # per round: paper draft, paper review
    ]
    return {"min": sum(p["min"] for p in parts), "max": sum(p["max"] for p in parts), "parts": parts}


def resolve(chain, settings):
    for key in chain:
        if str(settings.get(key) or "").strip():
            return str(settings[key]).strip()
    return settings.get("MODEL") or "openrouter/free"


def model_for_role(role, settings):
    if settings.get("DEMO_MODE") and ROLE_KEYS.get(role):
        return "Demo simulator (offline)"
    key = ROLE_KEYS.get(role)
    if not key:
        return {"retriever": "OpenAlex API", "parser": "Crossref + pypdf", "system": "Local Python"}.get(role, "Rules engine")
    return resolve([key], settings)


def describe(settings):
    steps = []
    for step in STEPS:
        slots = []
        for slot in STAGE_MODEL_SLOTS.get(step["id"], []):
            slots.append({"key": slot["key"], "label": slot["label"],
                          "value": str(settings.get(slot["key"]) or ""),
                          "effective": resolve(slot["chain"], settings),
                          "inherits": next((k for k in slot["chain"][1:] if settings.get(k)), "MODEL")})
        model = ("Demo simulator (offline)" if settings.get("DEMO_MODE") and slots else
                 slots[0]["effective"] if slots else SERVICES.get(step["id"], "Rules engine"))
        steps.append(dict(step, model=model, model_slots=slots))
    return steps
