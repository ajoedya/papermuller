# Full-text access for selected papers

The evidence stage now attempts full-text access after source selection. This
extends the local PDF workflow; it does not grant access to subscription content.

## Workflow

1. OpenAlex discovery retains up to three distinct `pdf_url` values from locations
   explicitly marked `is_oa`. The application does not construct guessed URLs.
2. DOI/title metadata checks run as before. A PDF or an OA PDF location makes a
   paper without an abstract eligible for provisional relevance screening.
3. Selected papers first use uploaded/cached text. With `FETCH_FULLTEXT=true`
   (default), live mode tries public OA PDF URLs when no cached PDF exists.
4. HTTPS, redirect destinations, byte count, PDF structure, page count, encryption,
   and extractable-text limits are checked. An automatically fetched PDF must
   contain the selected DOI or the normalized title in its first two pages;
   this is a heuristic identity check, not independent bibliographic proof.
5. PDF text is divided into bounded, page-labelled chunks. Every nonblank extracted
   text character is included, including text on long pages and the final page.
   No per-page truncation or four-excerpt cap applies to this extraction pass.
6. The evidence model receives each chunk, with paper text treated as untrusted
   data. Quotes are checked against the actual chunk and page. Grounded notes from
   all chunks are reduced in bounded groups to a source summary. Invalid synthesis
   quotes stop processing instead of being accepted as evidence.
7. Later writing/review stages receive evidence summaries and page-grounded
   excerpts. The claim audit explicitly includes the selected evidence page even
   when lexical ranking would omit it. All PDFs are not packed into every prompt.

`4_source_manifest.json` records access origin, failure reason, source hash,
page count, reading status and evidence page. `4_fulltext_reading.json` records
processed/total chunks, text/PDF pages, per-chunk character counts and grounded
notes. Reports use atomic file replacement. Incomplete model calls never mark a
paper fully processed. Reading in demo mode is explicitly marked simulated.

The results page displays **Full-text access & reading**, including when strict
mode stops the run before a matrix/draft is available. Raw downloaded PDFs remain
in the ignored local library, not in the research bundle.

## Settings and limits

- `FETCH_FULLTEXT=true`: fetch OA PDFs for selected sources in live mode. An
  uploaded/cached PDF is still usable when this setting is false.
- `REQUIRE_FULLTEXT=false`: permit explicit abstract-only fallback. When true,
  missing full text stops drafting and identifies the missing sources.
- Same PDF limits as uploads: 12 MB, 150 pages, and 900,000 extracted characters.
  Pages are no longer silently shortened to 18,000 characters.
- Images, scans, equations and tables without extractable text are not understood
  visually by this implementation. OCR/visual review is separate. Coverage reports
  distinguish pages with text from the total number of PDF pages.
- Chunking adds model requests and cost. Normal API telemetry records them under
  evidence extraction. A processed chunk means text reached the configured model;
  it does not certify comprehension or scientific correctness.
- HTML-only OA articles, publisher login pages, denied downloads, identity
  mismatches, and unsupported/encrypted/scanned PDFs produce explicit fallback
  reasons. OpenAlex coverage and publisher availability still limit retrieval.

## Networking

PDF destinations must use HTTPS without embedded credentials or custom ports.
Private/local address destinations and redirects are rejected. Direct connections
are pinned to a validated numeric address to avoid DNS rebinding. Redirects and
response sizes are bounded; TLS verification remains enabled. Proxy-side DNS is
allowed only for a short explicit set of known public publishing hosts when local
DNS resolution is unavailable; unknown hosts fail closed in that situation.

The first publisher test encountered a proxy 403. A configuration draft was saved
with `api.openalex.org`, `api.crossref.org`, `openrouter.ai`, and
`journals.plos.org`, preserving the package-manager preset. Subsequent checks in
this running instance successfully fetched Crossref metadata and a real PLOS PDF.
This is current-instance evidence, not proof that the saved draft was published
or that access will persist in a new task. Review and save environment settings,
then publish the environment to activate the reusable configuration. Other
publishers/CDN redirects need their actual hostnames added when selected; no
wildcard Internet permission was requested.

## Validation

All 53 automated tests passed. New full-text tests exercise:

- Public OA location discovery and private/credential/redirect rejection.
- Managed-proxy DNS restrictions, non-PDF responses, and download-size limits.
- Identity mismatch rejection, successful cached acquisition, and offline fallback.
- Complete chunk coverage through the final page and preservation of long pages.
- Grounded synthesis, per-page quote matching, and incomplete-reader reporting.
- Strict-mode stop before model extraction when full text is unavailable.
- PDF eligibility without abstracts and inclusion of evidence pages in audit prompts.

The full demo and strict-mode failure path were also exercised in Chromium at
390, 768, and 1440 px. A real PLOS paper, "Sharing Detailed Research Data Is
Associated with Increased Citation Rate" (DOI `10.1371/journal.pone.0000308`), was
fetched from the publisher and matched against Crossref metadata. Its five pages
yielded 31,137 extracted characters in three chunks; chunk character totals
matched the extracted text exactly. The fontTools dependency was added after this
PDF exposed a CFF-font decoding warning. Re-extraction with that dependency
succeeded without the warning. `pip check` also passed.

Live full-text model processing was not tested using billable model calls;
model calls in coverage tests are mocked and input coverage is asserted.
