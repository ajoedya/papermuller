# Papermuller

**Papermuller is an evidence AI Research & Writing Lab** that runs locally on your computer. It helps researchers discover and screen academic literature, inspect text-based PDF sources, build an auditable evidence ledger, draft a literature review, and assemble a working manuscript—all through a visual, interactive research pipeline.

> **Research prototype, not an autonomous researcher.** AI-generated claims, citations, methods, results, and interpretations require human verification. An AI review score is not a substitute for peer review or the requirements of your institution or journal.

## Features

- **Interactive research pipeline:** Twelve connected stages show what is running, complete, pending, or blocked. Click a node to inspect its inputs, outputs, model configuration, and execution telemetry.
- **Literature discovery and verification:** Search OpenAlex and check publication identifiers against Crossref.
- **PDF-assisted evidence extraction:** Upload text-based academic PDFs, link them to a DOI, and trace extracted passages to their PDF page.
- **Evidence-first checks:** Flag unknown citation IDs, missing references, unsupported or incomplete evidence mapping, and high-risk reviewer findings.
- **Researcher-approved scope:** Review and edit the research questions and scope before the pipeline continues.
- **Working manuscript:** Produce a literature review and an IMRaD-oriented manuscript scaffold without inventing empirical methods or results.
- **Full paper with a release gate:** After the literature review passes, AI drafts the title, abstract, introduction, discussion and conclusion. Methods and Results come only from your own text. A final AI review (scored by code, with no-fabrication and scope gates) must pass, and your checklist must be complete, before `9_paper_final.md` and `.docx` are written; otherwise the paper is saved as a stamped draft.
- **Multi-model routing:** Choose different OpenRouter models for evidence extraction, writing, claim verification, and review.
- **Local demo mode:** Explore the workflow with simulated data before configuring live APIs.

## Quick start

**Requirements:** Python 3.11 or newer. Internet access and API credentials are needed for live research; demo mode runs offline once the dependencies are installed.

```bash
python -m pip install -r requirements.txt
```

Create your local settings file:

```bash
# macOS / Linux
cp env.example .env

# Windows Command Prompt
copy env.example .env
```

Then start the local server:

```bash
python app.py
```

Open **http://localhost:8765** in your browser. By default, the server binds to **127.0.0.1** (your own computer).

On Windows, extract the project and double-click `Setup.bat` once, then `Start.bat`.
The launchers use a local `.venv`, preserve existing settings and research files,
and require Python 3.11 or newer. See [the laptop setup guide](docs/LOCAL-LAPTOP.md).

### Demo mode vs. live mode

`DEMO_MODE=true` is the default. It uses simulated research data and does **not** make actual AI or literature-database requests.

To run a live research project:

1. Copy `env.example` to `.env`.
2. Enter your `OPENROUTER_API_KEY` and, where applicable, your `OPENALEX_API_KEY`.
3. Set `DEMO_MODE=false`.
4. Review the model settings and provider pricing before starting.

You can configure supported settings from the local app interface as well.

**Security:** Never commit `.env`, API keys, licensed article PDFs, or the contents of `projects/` and `library/`. If a credential has previously been exposed, rotate it.

## The visual research pipeline

![Papermuller research workflow](docs/screenshots/workspace-desktop.png)

The workflow is drawn as a node flowchart: the research topic and the optional PDF library feed the ten stages, the researcher's approval sits between planning and the search, and a dashed loop shows the draft → audit → review revision cycle. On narrow screens the same graph is drawn top to bottom.

| Step | Stage | What happens |
| --- | --- | --- |
| 1 | **Research setup** | Propose a title, research questions, keywords, and scope; obtain researcher approval. |
| 2 | **Literature discovery** | Search OpenAlex for candidate publications. |
| 3 | **Source verification & PDF matching** | Check DOI metadata via Crossref and associate uploaded local PDFs when the DOI matches. |
| 4 | **Relevance screening** | Select publications related to the approved questions and scope. |
| 5 | **Evidence extraction** | Build an evidence matrix from abstracts or selected PDF text and record the source location. |
| 6 | **Literature synthesis** | Identify themes, comparisons, and research gaps; construct an outline. |
| 7 | **Drafting** | Write the literature review and prepare revisions. |
| 8 | **Citation & claim audit** | Validate citation identifiers and assess evidence support. |
| 9 | **Adversarial review** | Critique the draft, research scope, and methodology-related claims. |
| 10 | **Export & human verification** | Save the draft, working manuscript, evidence ledger, audit results, and researcher checklist. |

Select any node in the flowchart to inspect its **inputs, outputs, status, configured/reported AI model, request count, and token or cost figures when available**. AI stages can be given their own model directly from that panel, and the literature-discovery node shows the active search filters.

The node status is derived from backend events rather than a fabricated progress animation. Steps 7–9 may repeat during revision cycles. Demo activity is explicitly identified as simulated.

## Configure AI models

Papermuller uses [OpenRouter](https://openrouter.ai/) to connect to AI models. The default `MODEL` is `openrouter/free`, which routes only to free models (subject to availability and daily limits). `openrouter/auto` may select **paid** models. You can override the default for each AI stage:

| Environment setting | Stage | Falls back to |
| --- | --- | --- |
| `PLAN_MODEL` | 1 Research plan | `MODEL` |
| `SCREEN_MODEL` | 4 Source selection | `MODEL` |
| `EVIDENCE_MODEL` | 5 Evidence extraction | `MODEL` |
| `OUTLINE_MODEL` | 6 Literature synthesis | `WRITER_MODEL`, then `MODEL` |
| `WRITER_MODEL` | 7 Draft writing | `MODEL` |
| `VERIFIER_MODEL` | 8 Citation & claim audit | `MODEL` |
| `REVIEW_MODEL` | 9 Critical review (scoring) | `MODEL` |
| `REDTEAM_MODEL` | 9 Critical review (red-team pass) | `REVIEW_MODEL`, then `MODEL` |
| `PAPER_MODEL` | 10 Full paper draft | `WRITER_MODEL`, then `MODEL` |
| `PAPER_REVIEW_MODEL` | 11 Final paper review | `REVIEW_MODEL`, then `MODEL` |

Set them by clicking a stage on the flowchart or under **Settings → AI models**. **Load model list from OpenRouter** fills the model fields with suggestions from OpenRouter's public catalogue (free models by default). Comma-separated entries act as fallbacks.

The inspector displays the actual model reported by OpenRouter **when that information is available**; before a request runs, it shows the configured model. With router models such as `openrouter/free` or `openrouter/auto`, a specific model is not guaranteed for every request.

## Research settings

Under **Topic & sources → Research settings** (or in `.env`):

| Setting | Meaning |
| --- | --- |
| `FROM_YEAR`, `TO_YEAR` | Publication-year window for the OpenAlex search (inclusive). Blank `TO_YEAR` means the current year. |
| `WORK_TYPE` | `any`, `article`, `review`, or `article_review`. |
| `OPEN_ACCESS_ONLY` | Only open-access works, which makes full-text PDFs easier to obtain. |
| `MIN_CITATIONS` | Skip works with fewer citations (0 = no minimum). |
| `CANDIDATES`, `MAX_PAPERS`, `MIN_VERIFIED` | How many works to check, keep, and require before drafting. |
| `REVISION_ROUNDS`, `TARGET_SCORE` | Revision limit and AI review threshold. |
| `LANGUAGE` | Draft language (English or Indonesian). |

The filters are sent to OpenAlex and the year range is re-checked locally. Each run saves the filters it used in `2_search_settings.json`.

**Usage reporting:** Token counts and costs appear only when the provider returns them. “Not reported” does not mean free. Simulated numbers in demo mode are not real usage or billing records.

## Researcher controls and outputs

**Approve the research plan.** Edit the working title, research questions, assumptions, and search terms before proceeding. The assistant must not silently invent a study location, time period, or research population.

**Read selected papers in full text.** Papermuller first uses uploaded PDFs, then
tries up to three OpenAlex locations explicitly marked open access for each selected
paper. It does not bypass logins or paywalls. Downloaded files must match the
selected DOI or title in their first pages. Available extracted text is sent to
the evidence model in page-labelled chunks, including the final chunk; validated
chunk notes are combined into a source summary. This uses more API calls than
abstract-only extraction. Other stages use the resulting evidence summary and
page-grounded excerpts, not every full PDF in one prompt.

Under **Topic & sources → Research settings**, automatic retrieval is enabled by
`FETCH_FULLTEXT=true`. Enable **Require full text** (`REQUIRE_FULLTEXT=true`) to stop
before drafting when any selected paper lacks usable PDF text. Otherwise unavailable
sources remain explicitly **abstract only**, with a reason. In demo mode, no PDFs
are fetched and reading is simulated. Uploaded PDFs can also be used offline.

**Full-text access & reading** in the results shows access status, extracted text
pages, and processed/total chunks. `4_source_manifest.json` records access and
provenance; `4_fulltext_reading.json` records chunk coverage and grounded notes.
Failed model calls leave the reading status **incomplete**. Downloads are cached
in the ignored local PDF library. A PDF without an abstract is eligible if an
uploaded PDF or an open-access PDF location exists.

PDFs are limited to 12 MB, 150 pages, and 900,000 extracted characters. Text is not
silently truncated per page. Scanned pages, visual figures, and non-extractable
tables require separate OCR/visual review. Full-text availability does not certify
scientific accuracy or that extracted text includes every visual detail.

**Inspect the evidence ledger.** Check quotations, source identifiers, and PDF page or abstract provenance. A matching text span establishes traceability, **not necessarily that a claim is scientifically justified**.

**Prepare a working manuscript.** The AI drafts the literature review; Methods and Results must come from researcher-supplied information or remain clearly marked placeholders. Papermuller does not fabricate empirical findings.

**Complete human verification.** The author must read the cited sources, verify interpretations, and follow applicable disclosure and research-integrity requirements.

Files are stored locally under `projects/<timestamp>/`. Depending on the workflow, useful artifacts include:

- `7_final_draft.md` — literature-review draft.
- `7_final_evidence_audit.json` — evidence audit results.
- `8_manuscript_working.md` — working manuscript.
- `8_evidence_ledger.csv` — source-linked evidence entries, if generated.
- `8_human_verification.json` — human-review checklist.

## Editorial checks and portable research files

After a run, **Draft & evidence → Editorial checks** shows local writing suggestions,
heading gaps, unknown citation IDs, missing author sections, and approximate prose
statistics. Each finding names the checked Markdown file and its line number.
The checker never rewrites text and is not an AI detector or scientific review.

Download `9_editorial_report.json` for the complete report and `9_references.bib`
for BibTeX metadata keyed by source IDs such as `P1`. Author displays may be
incomplete; check the records before using them in a submission.
**Download research bundle (ZIP)** packages the current numbered research outputs,
including available Markdown, Word, evidence files, and BibTeX. It excludes API
settings, logs, original PDFs, and symlinks. The archive reflects the current
run's review/release status; it does not certify that the manuscript is complete.

These additions adopt document-checking and packaging ideas from
[MenulisCep4t](https://github.com/FRCHN-GSTN/MenulisCep4t) using an original Python
implementation. See [the comparison and adoption review](docs/MENULISCEPAT-ADOPTION.md)
for source snapshots, implementation scope, and remaining issues.

## Development and tests

Install the test dependencies and run the unit tests:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests cover evidence checks, PDF import, local endpoints, model routing, and pipeline telemetry. **Live integration with OpenRouter, OpenAlex, and Crossref must still be tested using your own credentials.**

The project currently uses a lightweight Python backend (`app.py`, `harness.py`, `stages.py`, `llm.py`, and related modules) with a local HTML interface.

## Limitations and responsible use

- Full-text extraction processes all available PDF text in chunks. Later drafting and auditing use summaries and selected page-grounded excerpts; figures and scanned content still need human review.
- OCR for scanned/image-only PDFs is **not yet included**.
- Matching DOI metadata or locating a quotation does **not** guarantee that an interpretation is correct.
- Literature selection may omit important studies, and AI review scores do **not** guarantee publishable academic quality.
- Empirical study design, data collection, analysis, methods, and results remain the researcher's responsibility.
- Real-model pricing, quotas, and availability depend on the provider. Check them before live use.
- The interface is available in **English and Indonesian** (switch with EN/ID in the top bar; the choice is remembered in your browser). Run-log lines and server error messages are still English. Draft output language is configured separately. `i18n.py` is retained for future localization of the command-line harness.

## License

See [LICENSE](LICENSE) for the repository's license.

---

**Papermuller's guiding principle:** make AI-assisted research easier to inspect and audit—not harder to question.

### Network access for full text

Live use needs HTTPS access to `api.openalex.org`, `api.crossref.org`,
`openrouter.ai`, and the actual open-access PDF hosts and their redirect
destinations. For example, PLOS uses `journals.plos.org`. Restricted cloud
allowlists must include each needed host. Unknown PDF hosts fail closed when
public DNS cannot be checked; managed proxy-side DNS is supported only for a
small explicit set of public publishing services (see `fulltext.py`). Keep TLS
verification enabled. Server error pages and inaccessible PDFs are reported as
abstract-only access failures, not as successfully read full text.
