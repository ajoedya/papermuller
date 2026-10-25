# Changelog

## Unreleased — Interactive Pipeline

- Papermuller-branded dark flowchart workbench with clickable 10-stage research graph, input/output/model inspector, activity timeline, and project tabs.
- Model assignments in settings for `EVIDENCE_MODEL`, `WRITER_MODEL`, `VERIFIER_MODEL`, and `REVIEW_MODEL`; actual model names from OpenRouter when provided.
- Real stage transitions, distinct demo simulation labels, per-stage request counts, optional provider-reported token/cost telemetry. No fictional percentages or costs.
- Keeps v4 full-text PDF provenance, audit gates, adversarial reviewer, IMRaD manuscript placeholders, human verification checklist.
- 21 offline tests; run using `python -m unittest discover -s tests -v`.

### Notes
- Local settings and files must never be committed to source control.
- The original repository's English/Indonesian web interface switch requires a follow-up migration; this UI is initially Indonesian.
- Live provider integrations and OCR require follow-up testing/development.
