# MenulisCep4t comparison and adoption

Reviewed 27 October 2026 (Asia/Makassar).

Source snapshots:

- [Papermuller](https://github.com/ajoedya/papermuller/tree/839af3e), main at review time.
- [MenulisCep4t](https://github.com/FRCHN-GSTN/MenulisCep4t/tree/ba5389fc518668f79e1b358b742786607df80cd1), default branch at review time.

## Current Papermuller

The repository has advanced beyond the earlier review: twelve workflow stages,
per-stage models, research filters, a complete-paper drafting pass, final AI
review, and Markdown/Word export already exist. Those features were preserved.
The interface defaults to English and now also offers an explicit Indonesian
language switch. This adoption keeps English as the default.

The product's most useful distinction remains quote and page provenance.
MenulisCep4t complements that with document inspection and editorial discipline.
It is primarily an academic-document engine/editor; its formatting tools do not
replace evidence retrieval or validate a scientific result.

## What was inspected in MenulisCep4t

README, package metadata, root MIT license, responsibility contract,
`references/pertahankan.md`, English writing-pattern guidance,
`scripts/periksa.py`, `scripts/report-doctor.py`, `scripts/report-stats.py`, and
`scripts/bundle.py`. The project describes components from laporan-generator,
naskah-id, and humanizer; their provenance should be retained if their code or
reference resources are copied in a later integration.

The implementation here is newly written Python code inspired by those
workflows. No scripts, reference text, templates, dictionaries, artwork, or
third-party dependencies from MenulisCep4t were copied or executed. No agent host
configuration or MCP registration was installed. The root repository is MIT, but
individual corpus/assets may have their own notices and were not imported.

## Adopted

| Source idea | Papermuller implementation | Limits |
| --- | --- | --- |
| Read-only manuscript checking with protected content | `editorial.py`, local English/Indonesian writing suggestions, file/line/excerpt/action | Small explicit rule set; not a complete EYD checker or authorship detector |
| Document doctor and statistics | Heading jumps, unknown citation IDs, missing author sections; prose-word, heading, and source counts | No statistical accuracy or journal compliance certification; counts exclude masked material |
| Markdown/BibTeX interoperability | `9_references.bib`, stable P-number source keys and DOI metadata | `@misc` records; author display strings may be truncated, so they are labeled in notes rather than fabricated into full author lists |
| Submission bundle | Current numbered Markdown, Word, CSV, JSON, and BibTeX outputs in a downloadable ZIP | Contains research content, not a publication-ready certification; excludes `.env`, logs, PDFs, directories, and symlinks |
| Review before editing | Suggestions do not change text or trigger AI rewrites | Appropriate hedging, quotations, numbers, and citations remain untouched |

The app displays the report in Draft & evidence. Each new completed run saves
`9_editorial_report.json` and `9_references.bib`. Saving a complete researcher
checklist through the app refreshes the report when a final paper is released.
The ZIP is assembled on download so it includes newly released outputs rather
than an outdated cached archive. Old runs still work without an editorial report.

Style checks exclude fenced/inline code, blockquotes, double-quoted passages,
URLs, and reference sections. Structure and citation checks include quoted
passages but still exclude code and references. The checker reports suggestions;
it never claims a text is AI-generated, changes scientific claims, or overrides
any existing evidence/release gate.

## Not adopted in this pass

- **Typst/Pandoc build system and campus presets:** valuable for thesis formatting,
  but require supported tool versions, metadata validation, template selection,
  and output-format tests. Papermuller's Word export is already present. A named
  journal/campus template should be implemented and tested before claiming
  standards compliance.
- **MCP/host synchronization:** useful for external agent clients, but unnecessary
  for the current browser workflow and introduces installation/configuration scope.
- **Automatic humanization:** a phrase checker cannot establish authorship and
  should not silently strengthen claims or rewrite quotations. This implementation
  only flags a small set of reviewable language patterns.
- **Full EYD/KBBI dictionary:** not appropriate as a mandatory English-interface
  dependency; Indonesian draft editing can be extended with separately maintained
  language resources and preserved attribution.

## Remaining issues in current Papermuller

1. `paper.py:release_final` trusts saved review status and the caller to enforce
   the checklist. Deterministic checks exclude author Methods/Results placeholders,
   so a nominally released paper may still contain missing sections. The editorial
   report now exposes them, but does not change release semantics. A stronger
   completion gate should distinguish a review scaffold from a complete article.
2. `tools.py:_get_json` collapses HTTP, network, and parsing failures into None;
   Crossref verification can label unavailable lookups as missing DOIs. These
   states must be separated before treating lookup failures as exclusion evidence.
3. `stages.py:stage_verify` still requires an abstract even if a source PDF exists;
   source screening sees only a short abstract. PDF-first eligibility remains useful.
4. Run state is still process-local and old run folders cannot be reopened through
   the UI. Persistence/recovery is higher priority than adding another AI role.
5. AI paper review does not add an independent deterministic claim-to-source audit
   for every newly generated Introduction/Discussion/Conclusion paragraph. Known
   citation IDs and reviewer scores alone do not establish support.
6. Writer/reviewer defaults can still resolve to the same model. Separate passes
   should not be described as independent validation.

These are review findings, not claims that live APIs were tested. Existing code
and release behavior outside the adoption were left intact.

## Validation

- 41 Python tests passed, including five new tests covering line locations,
  protected quotations/code, preserved manuscript content, missing author sections,
  BibTeX escaping/key validation, ZIP scoping, full demo output generation, result
  API exposure, BibTeX download, and current-run-only ZIP access.
- Chromium demo walkthrough exercised the report, BibTeX link and real ZIP download;
  ZIP contents were inspected. Responsive widths: 390, 768, and 1440 pixels.
- No live literature/model APIs or paid calls were needed. MenulisCep4t itself was
  inspected, not installed, built, or independently validated.

## Full-text follow-up

The subsequent full-text implementation fixes PDF eligibility without abstracts
and replaces the extraction-stage excerpt cap with complete chunked text reading.
See [Full-text access](FULLTEXT.md) for acquisition, coverage, strict mode, limits,
and current cloud-network requirements. The release, persistence and broader
scientific-audit findings above remain separate issues.
