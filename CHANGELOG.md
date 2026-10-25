# Changelog

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
