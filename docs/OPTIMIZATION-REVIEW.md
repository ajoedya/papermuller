# Repository optimization review

Reviewed 27 October 2026 against `main` at `06e7b63`, including the later working
changes described here. Scope: Python orchestration, full-text reading, evidence
checks, model/metadata clients, settings/API, exports, browser language controls,
and existing regression tests. This is not a complete security or linguistic audit.

## Assessment

The app has a useful end-to-end workflow, but its highest-value improvements are
correct language handling, dependable failure reporting, restart recovery, and
source-grounded review. Additional model roles should follow those improvements.
The current update implements bounded changes in the first three areas below;
it does not replace the application architecture or certify scientific quality.

## Implemented

### Paper language is independent of interface locale

The previous selector exposed English/Indonesian only, and `fillSettings` converted
any other stored value to English. Headings were fixed in English. Abstract and
quote validators assumed whitespace-delimited words.

The selector is now a free-form, validated language/locale field with suggestions.
`writing.py` centralizes language rules, common section labels, script-aware length
measurement, and prompt instructions. Unknown languages are accepted and their
heading labels are supplied by the drafting model. Common localized headings have
fallbacks, including traditional Chinese. Word documents retain language metadata
and an Arabic direction default. PDF page retrieval also uses bigrams for unspaced
scripts. Editorial reports recognize translated/custom bibliography headings and
use character counts when appropriate.

Paper-language values persist across API round trips, page reloads and UI locale
switches. They apply to planning/title/questions, synthesis, literature-review
prose and full-paper drafting. Planner search keywords remain English suggestions
that the researcher can edit separately. Source quotes, IDs and author-supplied
Methods/Results are preserved. Unknown language names are configuration data, not
additional model instructions; markup/control characters are rejected.

The missing-results marker is `[PENDING_AUTHOR_RESULTS]`, independent of language.
Legacy `[pending author analysis]` drafts are understood, but an arbitrary word
“pending” no longer satisfies that check. A Japanese/Chinese abstract is measured
in characters; normal spaced prose uses words. These are practical length checks,
not a complete tokenizer or language-identification service. Model support and
human review remain necessary. Demo prose remains scripted English.

### Final release checks are enforced inside the exporter

Previously `release_final` trusted a saved status, even when directly called
without a complete checklist or when author Methods/Results were missing.
It now requires passing review flags, completed author sections, and a saved
checklist covering the exact source IDs and required checks. Remaining completion
markers block release. Incomplete work remains downloadable as a stamped draft.
The browser explains that completing checkboxes cannot fill absent author data.

This change does not retrospectively delete previously exported files or provide
versioned approval history. Older saved runs lacking the new completion metadata
need regeneration before the new release function accepts them.

### Literature-service failures retain their meaning

Only HTTP 404 becomes a missing resource. Authorization, quota, timeout/network,
and malformed-response failures raise a typed `LiteratureServiceError` rather
than silently excluding a source as nonexistent. Transient failures receive at
most three attempts; Retry-After is honored within a five-second wait budget and
longer waits stop with an availability error. Connection checks display the error.
No provider error body or API-key-bearing URL is copied into the user message.

This still checks Crossref coverage, not every DOI registration agency. A missing
Crossref record is not proof that an article is fabricated.

### Repeated data work is bounded

- Extracted PDF pages have an LRU cache of at most 16 file revisions, keyed by
  resolved path, nanosecond modification time and byte size. Repeated audit rounds
  reuse unchanged text; changed files invalidate the cache. No model response or
  scientific decision is cached by this optimization.
- The results API returns full-text reading counters instead of all chunk notes.
  Full notes remain in the downloadable JSON report. A regression fixture with a
  50,000-character note checks that the summary stays below 400 serialized bytes;
  this is a targeted payload check, not an app-wide performance benchmark.
- Empty/malformed model responses receive controlled retry handling instead of
  IndexError/TypeError. Unknown-model HTTP 404 is not retried as transient failure.

## Highest remaining priorities

| Priority | Finding | Next concrete change |
| --- | --- | --- |
| High | Active state and job coordination are process-local; a restart loses UI access to saved runs | Persist run metadata/checkpoints, add reopen/history, then resume/cancel controls |
| High | Newly generated full-paper sections rely heavily on reviewer scores for claim support | Run the paragraph-to-source ledger audit on Introduction/Discussion/Conclusion as well |
| High | No hard run budget or context-size planning for potentially dozens of PDF chunks | Estimate chunk calls/tokens before live runs; enforce user-set call/cost/context limits |
| High | Threaded job admission and process-global stdout/observer can race across tabs | Introduce locked job transitions and job-local logging/events |
| Medium | Discovery uses capped results, mandatory Crossref matching and limited metadata | Add pagination, registration-agency fallback, richer bibliographic metadata, and explicit source decisions |
| Medium | Word output uses a small Markdown subset and generic formatting | Test real templates, tables/equations, CJK fonts and RTL layout in actual Word/LibreOffice |
| Medium | Approval artifacts are not versioned or bound to a document revision | Add content hashes and approval history; define behavior when a saved checklist changes |
| Medium | Python dependency ranges float and native Windows execution is untested here | Add reproducible constraints and Windows CI for Setup/Start and exports |

## Validation

All 68 Python tests passed. The regression suite covers custom-language API persistence, locale preservation,
French/custom headings, unchanged author numbers and source quotations, prompt
language propagation, CJK abstract/citation/evidence handling, language-neutral
missing-results markers, Arabic Word metadata/direction, and blocked release for
missing data or incomplete/mismatched checklists. Reliability tests cover HTTP
semantics/retries, malformed model output, cache reuse/invalidation, and slim API
summaries. Existing PDF/full-text, research filters, model routing, demo and export
checks remain in the suite.

Chromium checks cover custom values (French, English UK, Sundanese, Japanese),
reload and EN/ID switching, widths 390/768/1440, a full demo with French headings,
and refusal to release an incomplete paper even after all checkboxes are ticked.
Demo prose was not presented as French model output. No live model calls, paid
translation checks, native Windows execution, typography rendering, or broad
performance/load benchmarks were performed for this update.
