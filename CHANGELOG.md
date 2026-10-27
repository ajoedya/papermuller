# Changelog

## Visible paper-language selection

- Move paper language above brainstorming and show the selected language in the
  workflow header. Provide a language list, a free-text custom language/locale,
  and a separate save action; preserve the choice when reloading or switching
  the interface language.
- New configurations leave `LANGUAGE` empty. Require a choice before brainstorming
  or planning, while allowing connection setup without one. Preserve existing
  explicit preferences, including English, and save a new choice when generating.
- Show a notice when a non-English language is selected in the scripted demo.
  Existing drafts and source quotations are not automatically translated.
- Validate with 92 Python tests and Chromium checks for required selection,
  Indonesian, custom Sundanese/fr-CA, Japanese planning, English (UK), responsive
  layout, and a full demo workflow. Provider calls remain simulated.

## Laptop workflow, session panel, and idea exploration

- Replace the wide zoomable canvas with vertical, readable stage cards, approval
  and revision links, and stage details that adapt to laptop and smaller screens.
- Move activity, the run log, token input/output and totals, provider-reported
  USD cost, API requests, and per-stage usage into a shared left session panel.
  Derive token totals per response only when both components are known, distinguish
  missing from zero usage, and mark partial reports. Preserve counts from idea
  exploration and connection checks when creating a plan.
- Add conversational AI brainstorming before problem formulation. Select a
  proposed direction, edit its questions, then generate and approve a plan with
  an explicit editable research problem. Preserve recent brainstorming context
  in the project's downloadable `0_brainstorm.json` and research ZIP.
- Use the planner model and selected paper language for brainstorming. Keep demo
  suggestions clearly scripted, and require approval before literature discovery.
- Admit one model job at a time so brainstorming, connection checks, planning and
  research do not overlap observers or logs. Bound in-memory log/context history.
- Validate with 89 Python tests and Chromium checks including 1366/1280 laptop
  widths, responsive stage details, idea refinement/selection, and a full demo.

## WFLabs router connection fixes

- Load models using the API base URL and key currently entered in Settings,
  including unsaved edits. Keep catalogue lookup independent of unrelated research
  settings and an outdated model selection.
- Add WFLabs/OpenRouter presets while preserving other HTTPS OpenAI-compatible
  gateways. Test connections saves visible settings before testing them.
- Report authentication, denied-model access, and quota errors for the actual
  gateway. Validate known provider/key/model mismatches and avoid sending a saved
  credential to a newly entered endpoint. Keep legacy OpenRouter keys scoped to
  OpenRouter.
- Try explicit model fallbacks for generic gateways after unknown models or
  exhausted transient retries. Preserve OpenRouter's server-side fallback array.
- Replace the placeholder default model with the WFLabs guide's example and
  document provider setup. Missing catalogue pricing does not imply free access.
- Validate with 80 Python tests and Chromium connection-form checks using mocked
  gateways; live WFLabs account access still needs the user's active key.

## Paper languages and reliability optimizations

- Free-form paper language/locale with persistent custom values, independent of
  interface language. Localized headings and Word language metadata; script-aware
  abstract length, citation/quote checks, and page retrieval for unspaced scripts.
- Require actual author Methods/Results and the full saved source checklist before
  releasing a final paper. Keep source quotations and author text unchanged.
- Separate failed literature lookups from genuine 404s, with bounded transient
  retries. Validate model response text before use; do not retry unknown models.
- Reuse unchanged extracted PDF text through a bounded revision-aware cache and
  send only full-text reading counters, not large chunk notes, to the results UI.


## Full-text reading, editorial outputs, and Windows setup

- Retrieve available open-access PDFs for selected papers, with uploaded/cached
  PDFs preferred. Read all extracted text in page-labelled chunks and save
  processing coverage and per-page evidence notes.
- Add optional full-text requirements, explicit abstract-only fallback, and source
  access/reading status in the results view. Papers without abstracts can use PDFs.
- Add local editorial diagnostics, metadata-only BibTeX export, and a current
  research-output ZIP that excludes settings, logs, original PDFs, and symlinks.
- Add Setup.bat and update Start.bat to use a Windows virtual environment while
  preserving existing settings, source PDFs, and projects. Add laptop setup and
  update documentation.
- Validate with 53 Python tests, browser demo/strict-mode checks, and real PLOS
  PDF retrieval/extraction. Native Windows launcher execution remains unverified.


## Unreleased — Full paper draft and final review gate

- Two new stages after the critical review. **10 Full paper draft:** the writing model drafts the title, abstract, keywords, introduction, discussion and conclusion around the reviewed literature review, citing only source-matrix IDs. Methods and Results are copied from the author's text unchanged, or stay as placeholders; with no author results, the abstract must say results are pending. **11 Final paper review:** code checks unknown citations, empty sections, leftover placeholders and abstract length; a reviewer model scores six criteria and the score is computed by code. The paper passes only with all checks passed, `no_fabrication` and `scope_fidelity` at 8 or more, and the average at `TARGET_SCORE`. Failing papers are revised up to `REVISION_ROUNDS` times and the best round is kept.
- Export is now stage 12. The paper is saved as `9_paper_draft.md` and `9_paper_draft.docx`, stamped with its gate result. `9_paper_final.md` and `.docx` are written only when the gate passed, the literature review was accepted, and every item of the researcher checklist is saved as checked.
- New model keys `PAPER_MODEL` (falls back to `WRITER_MODEL`) and `PAPER_REVIEW_MODEL` (falls back to `REVIEW_MODEL`).
- New dependency: `python-docx` for Word export. Without it, Markdown is still written and the log says how to install it.
- The demo scripts a first full paper that invents a result, which the gate catches, and a second that passes.

## Unreleased — Flowchart workflow, per-stage models, research settings

### Interface
- The research workflow is drawn as a node flowchart: topic and optional PDF library feed the ten stages, researcher approval sits between planning and search, and a dashed loop marks the draft → audit → review revision cycle. Nodes show live status (waiting, running, done, failed) from backend events; edges into the active stage animate (disabled with reduced motion).
- Selecting a node opens a stage panel with its purpose, input/output, model usage, and editable model slots. The discovery node shows the active search filters.
- Narrow screens get a top-to-bottom version of the same graph; the canvas supports zoom and drag-to-pan.
- English/Indonesian interface switch (EN/ID, remembered per browser). Run-log lines and server errors remain English.
- Dark theme by default with a light theme toggle.

### Models
- New per-stage model keys: `PLAN_MODEL`, `SCREEN_MODEL`, `OUTLINE_MODEL` (falls back to `WRITER_MODEL`), and `REDTEAM_MODEL` (falls back to `REVIEW_MODEL`), alongside the existing `EVIDENCE_MODEL`, `WRITER_MODEL`, `VERIFIER_MODEL`, and `REVIEW_MODEL`.
- Default `MODEL` changed from `openrouter/auto` (may use paid models) to `openrouter/free`.
- Optional model suggestions loaded from OpenRouter's public model catalogue, free models by default.
- The AI disclosure template lists the model configured for each stage.

### Research settings
- Publication window `FROM_YEAR`–`TO_YEAR`, `WORK_TYPE` (article, review, or both), `OPEN_ACCESS_ONLY`, and `MIN_CITATIONS`, sent to OpenAlex as filters; the year range and citation minimum are re-checked locally.
- Candidate, retained, and minimum paper counts, revision rounds, review threshold, and draft language can be edited before each run and are saved with the plan.
- Each run records the filters it used in `2_search_settings.json`.
- Settings are validated in one place (`harness.parse_settings`) for both the web app and the command-line harness; the settings API accepts partial updates.

### Housekeeping
- `Mulai.bat` removed; `Start.bat` is the single Windows launcher, with an English and Indonesian message.
- 29 offline tests; run with `python -m unittest discover -s tests -v`.

### Still to verify with live credentials
- OpenAlex filter behaviour (`type`, `is_oa`, `cited_by_count`), the OpenRouter model catalogue request, and live provider routing for per-stage models.
- OCR for scanned PDFs is still not included.

## Earlier — Interactive pipeline

- Ten-stage research pipeline with researcher plan approval, Crossref metadata checks, PDF provenance, evidence and citation audits, adversarial review, IMRaD manuscript scaffold, and human verification checklist.
- Per-request model and usage telemetry from OpenRouter when reported; no fabricated percentages or costs.
