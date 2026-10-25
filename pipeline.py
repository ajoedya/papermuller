"""Stable, honest UI descriptions for the local research pipeline.

Stages report actual transitions; percentage, cost and tokens are intentionally
not fabricated when an upstream provider does not supply them.
"""

STEPS = [{'id': 1,
  'name': 'Research plan',
  'summary': 'Define questions and approve the scope',
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
  'name': 'Export & review',
  'summary': 'Save the manuscript, evidence ledger, and checklist',
  'engine': 'Python',
  'input': 'Selected draft and audit',
  'output': 'Local files for researcher review',
  'role': 'system'}]

ROLE_KEYS = {"planner": "MODEL", "retriever": None, "parser": None,
             "screen": "MODEL", "evidence": "EVIDENCE_MODEL", "writer": "WRITER_MODEL",
             "verifier": "VERIFIER_MODEL", "reviewer": "REVIEW_MODEL", "system": None}


def model_for_role(role, settings):
    if settings.get("DEMO_MODE") and ROLE_KEYS.get(role):
        return "Demo simulator (offline)"
    key = ROLE_KEYS.get(role)
    if not key:
        return {"retriever": "OpenAlex API", "parser": "Crossref + pypdf", "system": "Local Python"}.get(role, "Rules engine")
    return settings.get(key) or settings.get("MODEL", "openrouter/auto")


def describe(settings):
    return [dict(step, model=model_for_role(step["role"], settings)) for step in STEPS]
