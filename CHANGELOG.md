# Changelog

## Unreleased — Continue a stopped run

- **Try again no longer starts over.** Every finished stage of a run is saved in the run folder (`_checkpoints/`): search, Crossref checks, selection, evidence extraction, outline, and each round's draft, claim audit and review, plus the red-team check and the full-paper rounds. After an error, **Continue from stage N** reads those back and repeats only the stage that failed. The old button is now **Start over**.
- A saved stage is reused only if what it depends on is unchanged: the plan (title, questions, search terms, scope), the search window, open-access and citation filters, the number of candidates and of selected articles, the draft language, and the PDF library. Switching to another model, or changing the minimum number of articles, the review threshold or the revision rounds, keeps the finished work. For the full paper, the author's Methods and Results text and the literature review must also be unchanged.
- When a run finishes with a step skipped after an error (a revision round, the red-team check or the full paper), the same button, **Retry the unfinished step**, repeats just that step.
- If the research plan itself failed, the button tries the plan again for the same topic. New endpoint `POST /api/resume`; `/api/status` reports `resume` (`"run"`, `"plan"` or empty).
- Not covered: a run cannot be continued after the app has been closed, because the page forgets it; the saved stages stay in the folder. A stage is repeated as a whole, so evidence extraction starts its batches again.

## Unreleased — Compact flowchart and token usage detail

- The workflow flowchart no longer runs off to the right. It fits the width of its panel: one row on a very wide screen, and on narrower screens it wraps into a snake (left to right, then right to left) that grows downward, with 3 to 13 columns and smaller nodes below 600 px. It redraws when the window or the stage panel changes size. The legend and zoom buttons moved into a bar under the chart so they no longer cover the last row, and the revision loops (stages 7 to 9 and 10 to 11) are explained in a note under the chart. A loop that would cross two rows is not drawn, and the note covers it.
- New **API token usage** table under the flowchart: for every stage and every model that actually answered, the number of responses, input tokens, output tokens, total, cost when the provider reports it, and, in small print, cached input and reasoning output tokens. Topic brainstorming has its own row. A response whose provider reported nothing shows a dash, not zero, and the footer says how many responses reported nothing. Requests that failed or were retried are not counted, because the provider reports usage only for answers.
- The stage panel now shows input and output tokens separately instead of one total.
- Each run writes the same table to `9_api_usage.csv` (blank cells for unreported usage, plus a TOTAL row), linked from the table.

## Unreleased — Topic brainstorming and paid model picker

- Stage 1 gains an optional brainstorming step. On **Topic & sources**, describe a field or rough idea and the AI suggests five distinct topics (topic, angle, why it is worth studying, search terms). **More ideas** adds new ones without repeating earlier ones, and **Use this topic** fills the topic box. Suggestions come from the model's general knowledge, not a literature search, and the prompt forbids invented countries, periods, citations or claimed gaps. The idea is sent to the model as data. New endpoint `POST /api/brainstorm` (blocked during a run).
- Brainstorming uses `PLAN_MODEL`, falling back to `MODEL`. The topic card has a model field for it, with **Load free models** and **Load paid models**.
- The model catalogue now reports prices per 1M input and output tokens, can list `free`, `paid` or `all` models, and sorts paid models cheapest first. Models with no real price (such as routers) show "price varies" instead of 0. Choosing a paid model shows its price and says it is billed to your OpenRouter balance. `POST /api/models` accepts `kind`; the old `free_only` still works.
- The catalogue request is public and sends no API key.
- A reset or timed-out connection, a cut-off reply, or an unreadable reply (for example `ConnectionResetError: [WinError 10054]`) no longer ends the run. It is retried like a busy model: up to 3 attempts, 20 seconds apart, then a plain `[AI ERROR] Connection problem (...)` message.
- If a revision round (stages 7 to 9) still fails after those retries, the run keeps the best draft from the earlier rounds instead of discarding everything. The draft stays marked provisional, and `7_final_review.json` records `interrupted` and a limitation. A failure in the first round still stops the run, since there is nothing to keep.
- OpenRouter limits some free models to approved agent apps and answers 403 "only available on agentic harnesses". Papermuller now drops such a model and tries the next one in the comma-separated list; with no backup it stops at once with a plain message naming the model and what to do, instead of showing the raw JSON. Other 403 errors are unchanged. The catalogue has no field that marks these models, so they cannot be filtered out of the list in advance.

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
