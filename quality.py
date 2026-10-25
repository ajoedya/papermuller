"""Deterministic, auditable checks for a literature-review workflow.

A real citation or verbatim quote is NOT proof that a scientific claim is true.
The complementary AI-assisted assessment lives in stages.py, with explicit
provisional status when this human-review step cannot be passed.
"""
import re
import unicodedata
from difflib import SequenceMatcher

CITE_PATTERN = re.compile(r"\[\s*(P\d+(?:\s*[,;]\s*P\d+)*)\s*\]", re.I)
ANY_ID = re.compile(r"\bP\d+\b", re.I)


def normalize_doi(doi):
    doi = str(doi or "").strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    return doi.split("?", 1)[0].strip().strip("/").lower()


def normalize_text(text):
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return re.sub(r"\s+", " ", text).strip()


def quote_is_in_abstract(quote, abstract):
    """Require a substantial, contiguous, verbatim passage (whitespace-insensitive)."""
    q = normalize_text(quote)
    return len(q) >= 25 and len(q.split()) >= 5 and q in normalize_text(abstract)


def title_similarity(expected, actual):
    def clean(s):
        return re.sub(r"[^\w\s]", " ", normalize_text(s)).split()
    left, right = clean(expected), clean(actual)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def prose_paragraphs(draft):
    """Extract numbered prose blocks, ignoring headers and code fences.

    One paragraph with a citation does not magically cover an unrelated claim
    elsewhere: the AI evidence audit checks each numbered paragraph separately.
    """
    blocks = re.split(r"\n\s*\n", str(draft or ""))
    paragraphs = []
    in_code = False
    for block in blocks:
        lines = []
        for line in block.splitlines():
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code or not line.strip() or line.lstrip().startswith(("#", "|", "---")):
                continue
            lines.append(line.strip())
        text = " ".join(lines).strip()
        if text and len(re.sub(r"\[[^]]+\]", "", text).split()) >= 8:
            paragraphs.append({"number": len(paragraphs) + 1, "text": text})
    return paragraphs


def paragraph_ids(text):
    found = []
    for match in CITE_PATTERN.finditer(text):
        for pid in ANY_ID.findall(match.group(1)):
            pid = pid.upper()
            if pid not in found:
                found.append(pid)
    return found


def citation_audit(draft, matrix):
    allowed = {str(row["id"]).upper() for row in matrix}
    paragraphs = prose_paragraphs(draft)
    used = set()
    uncited = []
    for para in paragraphs:
        citations = paragraph_ids(para["text"])
        para["cited_ids"] = citations
        used.update(citations)
        if not citations:
            uncited.append(para["number"])
    unknown = sorted(used - allowed)
    return {
        "allowed_ids": sorted(allowed),
        "used_ids": sorted(used),
        "unknown_ids": unknown,
        "uncited_paragraphs": uncited,
        "paragraphs": paragraphs,
        "passed": bool(paragraphs) and not unknown and not uncited,
        "coverage": round(len(used & allowed) / len(allowed), 3) if allowed else 0,
    }


def validate_evidence_audit(raw, citation_report, papers, sources=None):
    """Cross-check model assessments against actual text and abstract passages.

    This prevents a model from claiming evidence was checked when its snippets
    do not exist in the supplied source, or when it omits an awkward paragraph.
    """
    by_id = {p["id"]: p for p in papers}
    sources = sources or {}
    provided = {}
    items = raw.get("items", [])
    if not isinstance(items, list):
        items = []
    for item in items:
        if isinstance(item, dict) and type(item.get("paragraph")) is int:
            provided.setdefault(item["paragraph"], item)
    assessments = []
    for p in citation_report["paragraphs"]:
        number = p["number"]
        model = provided.get(number, {})
        label = str(model.get("status", "unclear")).lower()
        if label not in ("supported", "partial", "unsupported", "unclear"):
            label = "unclear"
        valid_quotes = []
        evidence = model.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            pid = ev.get("id")
            quote = ev.get("quote", "")
            if pid not in p['cited_ids'] or pid not in by_id:
                continue
            if pid in sources:
                from sources import quote_location
                requested = ev.get('page')
                if type(requested) is not int:
                    requested = None
                page = quote_location(sources[pid], quote, requested)
                if page is not None:
                    valid_quotes.append({'id': pid, 'quote': quote, 'page': page,
                                         'source_type': sources[pid]['source_type']})
            elif quote_is_in_abstract(quote, by_id[pid].get('abstract', '')):
                valid_quotes.append({'id': pid, 'quote': quote, 'page': 0,
                                     'source_type': 'abstract_only'})
        # No excerpts? Then a model's confident 'supported' assessment is NOT trusted.
        if label == "supported" and not valid_quotes:
            label = "unclear"
        # At least one anchored excerpt per cited paper for 'supported' status.
        if label == "supported" and any(pid not in {ev["id"] for ev in valid_quotes} for pid in p["cited_ids"]):
            label = "partial"
        if not p["cited_ids"] or any(pid not in by_id for pid in p["cited_ids"]):
            label = "unsupported"
        assessments.append({
            "paragraph": number, "status": label, "cited_ids": p["cited_ids"],
            "evidence": valid_quotes, "reason": str(model.get("reason", ""))[:500],
        })
    passed = citation_report["passed"] and bool(assessments) and all(x["status"] == "supported" for x in assessments)
    return {"passed": passed, "paragraphs": assessments,
            "supported": sum(x["status"] == "supported" for x in assessments),
            "total": len(assessments),
            "note": "Audit AI dengan jejak kutipan abstrak atau halaman PDF; bukan verifikasi ilmiah penuh."}
