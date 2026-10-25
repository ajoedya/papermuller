# Papermuller

**Papermuller is an evidence-first AI Research & Writing Lab** that runs locally on your computer. It helps researchers discover and screen academic literature, inspect text-based PDF sources, build an auditable evidence ledger, draft a literature review, and assemble a working manuscript—all through a visual, interactive research pipeline.

> **Research prototype, not an autonomous researcher.** AI-generated claims, citations, methods, results, and interpretations require human verification. An AI review score is not a substitute for peer review or the requirements of your institution or journal.

## Features

- **Interactive research pipeline:** Ten connected stages show what is running, complete, pending, or blocked. Click a node to inspect its inputs, outputs, model configuration, and execution telemetry.
- **Literature discovery and verification:** Search OpenAlex and check publication identifiers against Crossref.
- **PDF-assisted evidence extraction:** Upload text-based academic PDFs, link them to a DOI, and trace extracted passages to their PDF page.
- **Evidence-first checks:** Flag unknown citation IDs, missing references, unsupported or incomplete evidence mapping, and high-risk reviewer findings.
- **Researcher-approved scope:** Review and edit the research questions and scope before the pipeline continues.
- **Working manuscript:** Produce a literature review and an IMRaD-oriented manuscript scaffold without inventing empirical methods or results.
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

On Windows, you can also double-click `Start.bat` or `Mulai.bat` after installing the dependencies.

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

Select any node in the flowchart to inspect its **inputs, outputs, status, configured/reported AI model, request count, and token or cost figures when available**.

The node status is derived from backend events rather than a fabricated progress animation. Steps 7–9 may repeat during revision cycles. Demo activity is explicitly identified as simulated.

## Configure AI models

Papermuller uses [OpenRouter](https://openrouter.ai/) to connect to AI models. You can set a general model and optionally override it for individual tasks.

| Environment setting | Purpose |
| --- | --- |
| `MODEL` | Default model, including research setup and screening. |
| `EVIDENCE_MODEL` | Literature matrix and evidence extraction. |
| `WRITER_MODEL` | Outline creation and drafting. |
| `VERIFIER_MODEL` | Claim-support auditing. |
| `REVIEW_MODEL` | Rubric evaluation and adversarial review. |

Overrides left blank use the default model. The same options are available in the app's configuration area. Comma-separated model entries can be used for fallback routing where supported.

The inspector displays the actual model reported by OpenRouter **when that information is available**; before a request runs, it shows the configured model. With `openrouter/auto`, a specific model is not guaranteed for every request.

**Usage reporting:** Token counts and costs appear only when the provider returns them. “Not reported” does not mean free. Simulated numbers in demo mode are not real usage or billing records.

## Researcher controls and outputs

**Approve the research plan.** Edit the working title, research questions, assumptions, and search terms before proceeding. The assistant must not silently invent a study location, time period, or research population.

**Import source PDFs.** The local library supports text-based PDF files up to **12 MB and 150 pages**, linked to their publication DOI. Scanned/image-only PDFs are not OCR-processed in this release.

**Inspect the evidence ledger.** Check quotations, source identifiers, and PDF page or abstract provenance. A matching text span establishes traceability, **not necessarily that a claim is scientifically justified**.

**Prepare a working manuscript.** The AI drafts the literature review; Methods and Results must come from researcher-supplied information or remain clearly marked placeholders. Papermuller does not fabricate empirical findings.

**Complete human verification.** The author must read the cited sources, verify interpretations, and follow applicable disclosure and research-integrity requirements.

Files are stored locally under `projects/<timestamp>/`. Depending on the workflow, useful artifacts include:

- `7_final_draft.md` — literature-review draft.
- `7_final_evidence_audit.json` — evidence audit results.
- `8_manuscript_working.md` — working manuscript.
- `8_evidence_ledger.csv` — source-linked evidence entries, if generated.
- `8_human_verification.json` — human-review checklist.

## Development and tests

Install the test dependencies and run the unit tests:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests cover evidence checks, PDF import, local endpoints, model routing, and pipeline telemetry. **Live integration with OpenRouter, OpenAlex, and Crossref must still be tested using your own credentials.**

The project currently uses a lightweight Python backend (`app.py`, `harness.py`, `stages.py`, `llm.py`, and related modules) with a local HTML interface.

## Limitations and responsible use

- PDF processing uses **selected text excerpts**, not exhaustive whole-document understanding; always read the original paper.
- OCR for scanned/image-only PDFs is **not yet included**.
- Matching DOI metadata or locating a quotation does **not** guarantee that an interpretation is correct.
- Literature selection may omit important studies, and AI review scores do **not** guarantee publishable academic quality.
- Empirical study design, data collection, analysis, methods, and results remain the researcher's responsibility.
- Real-model pricing, quotas, and availability depend on the provider. Check them before live use.
- The v5 flowchart interface is currently in **Bahasa Indonesia**. The older UI's language switch has not yet been fully migrated; the manuscript's output language remains configurable. `i18n.py` is retained for future localization.

## License

See [LICENSE](LICENSE) for the repository's license.

---

**Papermuller's guiding principle:** make AI-assisted research easier to inspect and audit—not harder to question.
