# Product, interface, and tool review

Reviewed 25 October 2026. Scope: the HTML interface, Python server, CLI harness,
research stages, OpenAlex/Crossref adapters, model client, PDF library, evidence
checks, manuscript generation, demo fixtures, translations, requirements,
documentation, and all three test modules. Live provider behavior was not tested.

## Assessment

Papermuller has a useful core: connecting draft claims to identifiable source
passages and retaining the evidence trail for a researcher. That is more useful
than the number of AI roles or a high reviewer score. Position it as a literature
review workbench. The manuscript export is a scaffold with missing sections, and
the search is a small relevance-ranked sample, not an exhaustive review method.

The strongest safeguards are deterministic: exact normalized quote matching,
page provenance, unknown-citation rejection, checks for omitted audit paragraphs,
researcher approval of scope, and explicit missing Methods/Results. Keep these.
They establish traceability; semantic support still depends on a model and human
judgment. A matching quote can accompany a mistaken interpretation.

## Interface changes made

- Replaced the dark dotted canvas, gradients, glass effects, decorative icons,
  model pills, and winding arrows with a quiet paper-colored workspace, readable
  type, a restrained green accent, and sequential stage rows.
- Added a state-dependent next action, including visible plan approval on phones.
- Removed duplicate visible navigation and hid the stage inspector on form pages.
- Replaced promotional and self-congratulatory copy with concrete task language.
  Clarified that metadata matches do not establish article findings, and that
  storage belongs to the machine running the server.
- Used clear English stage and model-role names. Reduced the reviewer
  score's visual weight and clarified that its target is not scientific accuracy.
- Fixed plan regeneration by resetting the approval state before requesting a new
  plan; preserved the topic. Previously the backend returned HTTP 409.
- Added inline request errors, restored the connection-test button after failure,
  and allowed status polling to recover after temporary network failures.
- Removed duplicate result fetching, used recorded completed stages in the
  progress list, and retained keyboard focus during stage rerenders.

## Remaining findings, ordered by priority

### High: service failures are treated as negative research evidence

`tools.py:_get_json` returns None for authorization errors, throttling, network
failures, malformed responses, and missing resources. `verify_doi` turns all of
these into “DOI not found in Crossref.” Search failures similarly become empty
results. This can exclude valid literature and mislead researchers about why.
Return structured outcomes for found, absent, unavailable, and unauthorized;
retry transient failures with bounded backoff; never classify an unavailable
lookup as a disproven DOI. Crossref also does not cover every DOI registration
agency. Report its coverage limitation explicitly.

### High: uploaded PDFs cannot rescue papers without abstracts

`stages.py:stage_verify` requires `paper['abstract']` even when a DOI-matched PDF
exists. Screening then sees only the first 350 abstract characters. This discards
usable sources and can make relevance decisions before seeing the relevant
passage. Accept a readable PDF as an alternative and screen using source excerpts.

### High: runs cannot be recovered through the app after a server restart

`app.py:STATE` lives in process memory, and downloads are restricted to the current
run. Saved folders survive but the interface cannot reopen them. A reset also
removes the current run from view. Add a persisted run index, project reopening,
checkpoint recovery, and explicit cancellation. Preserve files already written.

### High: review is correlated, not independent validation

The writer, verifier, reviewer, and challenge pass can resolve to the same default
model. Asking a model to behave as an independent reviewer does not establish
independence. Scope acceptance also rests on a model-generated score of at least
8. Describe these as separate passes and use deterministic scope checks where
possible. Test with intentionally plausible but unsupported claims and evaluate
against human-labeled examples. Different models may reduce shared blind spots,
but do not establish scientific validity.

### Medium: model transport and response validation are incomplete

`llm.py:_send` assumes a nonempty choices array, a message, and string content.
Timeouts and connection failures do not receive the retry handling used for
selected HTTP errors. `ask_for_json` checks JSON syntax, but most stage outputs
lack a complete schema. Add typed validation and bounded retry policies. Record
failed attempts separately from successful responses, honor Retry-After, and set
output-token and run-cost limits. Current cost reporting observes spending after
responses; it does not enforce a budget.

### Medium: threaded writes and job admission can race

The server is threaded, while checking the phase and starting a job are separate
operations. Two concurrent plan requests can both pass the admission check.
stdout and the model observer are process globals; settings and PDF index writes
are not atomic. Use one locked job transition, job-local logging/observers, and
atomic replacement for settings and library metadata. This matters even for a
single researcher using multiple tabs.

### Medium: the research sample is narrow and has selection bias

Search takes at most 15 results per keyword and caps the merged candidate list.
It excludes sources without DOIs, uses Crossref matching as a mandatory gate, and
requires abstracts. A negative search-gap conclusion cannot be supported from
this sample alone. Retain query/date/rank/filter provenance, show exclusion
reasons, allow manual source inclusion, and offer pagination. Keep claims about
coverage modest.

### Medium: extraction quality is narrower than its labels suggest

`relevant_snippets` ranks short chunks by lexical overlap. Only a few excerpts
reach the model. `evidence_text` still labels the method “from abstract” for PDF
sources. Exact quote presence does not validate extracted methods, limitations,
or generalizations. Show the selected excerpts alongside each extracted field,
expose missing evidence, and evaluate field accuracy separately from quote matches.
A DOI supplied by the uploader also does not prove that the PDF belongs to it.

### Medium: settings are file-only and the UI exposes few controls

`harness.py:load_settings` reads .env instead of process environment bindings.
Cloud-injected credentials therefore will not automatically configure the app.
The UI lacks year, candidate-count, minimum-source, revision-limit, and budget
controls. Add a documented configuration precedence and validated controls.
Keep secrets out of responses and exported settings. `.env` is plaintext storage.

### Medium: source review needs more direct interaction

The interface exposes a wide matrix and downloadable files, but no side-by-side
claim/excerpt viewer, source-page navigation, source exclusion editor, or run
history. These are higher-value next features than additional agent roles.
The folder-opening action is Windows-only; the UI now labels that limitation.

### Lower priority: cleanup and reproducibility

- `i18n.py` describes an older workflow and is not used by the current interface;
  translation and quota/pricing claims can drift. Consolidate or retire it.
- Demo data is fictional and scripted, ignores the topic, and can deliberately
  demonstrate mistakes. Its semantic audit is scripted; demo success is not
  evidence of live factual accuracy. Label fictional sources within exports too.
- Dependency ranges are broad and there is no lockfile or CI workflow in this
  checkout. Add reproducible dependency resolution and automated checks.
- The handwritten Markdown renderer supports a small subset; test real exported
  drafts with blockquotes, lists, tables, and links before expanding it.
- The single HTML file mixes styling, rendering, network calls, and workflow
  state. Separate these concerns as the interface grows; keep the current simple
  runtime until the product needs a framework.

## Validation performed

- All 22 Python tests passed (including an English-interface regression check), including PDF import/page provenance,
  evidence and scope gates, endpoint protections, and demo pipeline tests.
- Chromium browser check passed: topic entry, plan creation, regeneration,
  approval, full offline demo, six matrix rows, and download-link rendering.
- Injected an HTTP 503 into the connection test: inline error appeared, the
  button re-enabled, and retry succeeded after the failure was removed.
- Stage keyboard focus survived a rerender. No browser page errors were recorded.
- No horizontal page overflow at widths 390, 768, and 1440 pixels. Desktop and
  phone screenshots were inspected. This is not a complete accessibility audit.
- `git diff --check` passed. No live APIs, paid calls, independent scientific
  evaluation, multiuser load, or malicious-PDF resource-exhaustion tests were run.

Recommended order: fix lookup error semantics and PDF eligibility, persist and
reopen runs, then build the claim/excerpt review view. Add budgets and stronger
model-response validation before encouraging substantial live usage.

## English interface follow-up

The application interface is English, including form labels, stage descriptions,
activity events, PDF validation errors, server errors, review checklists, and
exported template instructions. Draft output language remains an independent
setting: new settings default to English, and existing preferences are preserved.
The English-interface regression test also runs with Indonesian draft settings.

## Addendum: flowchart redesign (same day)

At the owner's request the stage list was replaced by a node flowchart modelled
on workflow-builder canvases (dark dotted canvas, icon nodes, curved
connectors). This reverses the earlier move to a paper-coloured list, so the
following safeguards were kept to preserve readability:

- Node states still come only from backend events; nothing is animated without
  a matching state change, and animation stops under `prefers-reduced-motion`.
- Every node is a real button with a text label and status in its accessible
  name; a light theme is one click away.
- Phones get a vertical graph rather than a shrunken horizontal one.
- Model choice per stage moved into the node panel, next to the stage it
  affects, with the inherited model shown when a slot is blank.
