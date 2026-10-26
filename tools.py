"""
tools.py  -  THE "HANDS"
========================
The AI can only think and write. It cannot visit websites by itself.
Tools are small functions that do real work for it:

  search_papers()  -> asks OpenAlex (a free database of 250M+ papers)
  verify_doi()     -> asks Crossref (the official DOI registry) if a paper is real

Both services are free and need no API key.
In DEMO mode, they return sample data instead of going online.
"""

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from quality import normalize_doi, title_similarity

USER_AGENT = "Papermuller/1.0 (+https://github.com/ajoedya/papermuller)"
RETRY_WAITS = (2, 6)  # seconds to wait before the second and the third attempt
RETRYABLE = (429, 500, 502, 503, 504)
HINTS = {401: "API key rejected", 403: "access refused (API key may be required)",
         404: "not found", 429: "daily limit reached or too many requests"}


class LookupFailed(Exception):
    """A web service could not be reached, or kept failing, after the retries.

    That is not the same as "no result": the answer is unknown."""


def _fetch(url):
    """Download a web address and read it as JSON, trying again when the problem is probably temporary.

    Returns ("ok", data), ("not_found", None) for a 404, or ("error", reason) after the last attempt."""
    reason = "no answer"
    for attempt in range(len(RETRY_WAITS) + 1):
        pause = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                return "ok", json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return "not_found", None
            reason = f"server said {error.code}: {HINTS.get(error.code, error.reason)}"
            if error.code not in RETRYABLE:
                print(f"   ! {reason}")
                try:
                    detail = error.read().decode("utf-8", errors="ignore").strip()
                except (OSError, http.client.HTTPException):
                    detail = ""
                if detail:
                    print(f"     details: {detail[:200]}")  # the server's own explanation
                return "error", reason
            try:
                pause = min(30, max(1, int(error.headers.get("Retry-After"))))
            except (TypeError, ValueError, AttributeError):
                pause = None
        except (OSError, http.client.HTTPException, ValueError) as error:
            # No connection, a dropped connection, a timeout, or an answer that is cut off or not JSON.
            reason = f"could not connect or read the answer ({type(error).__name__})"
        if attempt < len(RETRY_WAITS):
            pause = pause if pause is not None else RETRY_WAITS[attempt]
            print(f"   ! {reason}. Trying again in {pause} s ({attempt + 2}/{len(RETRY_WAITS) + 1})...")
            time.sleep(pause)
    print(f"   ! {reason}. Giving up on this request.")
    return "error", reason


def _get_json(url):
    """Download a web address and read it as JSON. Returns None on failure."""
    status, data = _fetch(url)
    return data if status == "ok" else None


def _rebuild_abstract(inverted_index):
    """OpenAlex stores abstracts in a scrambled form. This puts the words back in order."""
    if not inverted_index:
        return ""
    positions = []
    for word, places in inverted_index.items():
        for place in places:
            positions.append((place, word))
    return " ".join(word for _, word in sorted(positions))


WORK_TYPE_FILTERS = {"article": "article", "review": "review", "article_review": "article|review"}


def openalex_filter(settings):
    """Build the OpenAlex filter string from the research settings (AND-combined)."""
    parts = [f"from_publication_date:{int(settings['FROM_YEAR'])}-01-01"]
    if settings.get("TO_YEAR"):
        parts.append(f"to_publication_date:{int(settings['TO_YEAR'])}-12-31")
    work_type = WORK_TYPE_FILTERS.get(settings.get("WORK_TYPE", "any"))
    if work_type:
        parts.append(f"type:{work_type}")
    if settings.get("OPEN_ACCESS_ONLY"):
        parts.append("is_oa:true")
    if int(settings.get("MIN_CITATIONS") or 0) > 0:
        parts.append(f"cited_by_count:>{int(settings['MIN_CITATIONS']) - 1}")
    return ",".join(parts)


def within_filters(paper, settings):
    """Local safety net: drop records outside the requested year range or citations."""
    year = paper.get("year")
    if isinstance(year, int):
        if year < int(settings.get("FROM_YEAR") or 0):
            return False
        if settings.get("TO_YEAR") and year > int(settings["TO_YEAR"]):
            return False
    return int(paper.get("cited_by") or 0) >= int(settings.get("MIN_CITATIONS") or 0)


def search_papers(keyword, settings, how_many=8, strict=False):
    """Search OpenAlex for papers matching `keyword`. Returns a list of paper dictionaries.

    With strict=True, a service that cannot be reached raises LookupFailed instead of looking
    like a search without results."""
    if settings["DEMO_MODE"]:
        from demo_data import fake_search
        return fake_search(keyword)

    # Kept to the simplest, most widely supported parameters.
    # (Papers without a DOI are dropped later, in stages.py.)
    params = {
        "search": keyword,
        "per_page": how_many,
        "filter": openalex_filter(settings),
    }
    if settings.get("OPENALEX_API_KEY"):
        params["api_key"] = settings["OPENALEX_API_KEY"]  # free key = 10x bigger daily budget
    elif settings.get("EMAIL"):
        params["mailto"] = settings["EMAIL"]  # older polite-access method, used only without a key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)

    status, data = _fetch(url)
    if status != "ok":
        if strict:
            raise LookupFailed(f"OpenAlex could not be reached for '{keyword}' ({data or 'not found'})")
        print(f"   ! OpenAlex did not answer for '{keyword}'")
        return []
    if not data:
        print(f"   ! OpenAlex returned nothing for '{keyword}'")
        return []

    papers = []
    for item in data.get("results", []):
        papers.append({
            "title": item.get("title") or "",
            "year": item.get("publication_year"),
            "authors": ", ".join(a["author"]["display_name"]
                                 for a in item.get("authorships", [])[:4]),
            "doi": normalize_doi(item.get("doi")),
            "abstract": _rebuild_abstract(item.get("abstract_inverted_index")),
            "cited_by": item.get("cited_by_count", 0),
            "openalex_id": item.get("id", ""),
            "publication_date": item.get("publication_date", ""),
        })
    time.sleep(0.5)  # be polite to the free service
    return papers


def check_doi(doi, expected_title, settings):
    """
    Ask Crossref: does this DOI really exist, and does its title match?
    Returns (state, reason). The state is "match", "mismatch", "not_found" or "invalid", or
    "unreachable" when Crossref did not answer: that says nothing about the DOI, so a real
    article must not be dropped as if it were invented.
    """
    if settings["DEMO_MODE"]:
        from demo_data import fake_verify
        ok, reason = fake_verify(doi)
        return ("match" if ok else "not_found"), reason

    doi = normalize_doi(doi)
    if not doi.startswith("10.") or "/" not in doi:
        return "invalid", "invalid DOI format"
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    if settings.get("EMAIL"):
        url += "?" + urllib.parse.urlencode({"mailto": settings["EMAIL"]})  # Crossref's polite pool: faster and steadier
    status, data = _fetch(url)
    time.sleep(0.3)
    if status == "error":
        return "unreachable", f"Crossref could not be reached ({data}); this does not mean the DOI is invalid"
    if status == "not_found" or not data:
        return "not_found", "DOI not found in Crossref"

    message = data.get("message") or {}
    titles = message.get("title") or []
    real_title = titles[0] if titles else ""
    real_doi = normalize_doi(message.get("DOI"))
    similarity = title_similarity(expected_title, real_title)
    if real_doi == doi and similarity >= 0.82:
        return "match", f"Crossref DOI + title match ({similarity:.0%}); content not checked"
    return "mismatch", f"metadata mismatch (title similarity {similarity:.0%}; Crossref: {real_title[:60]})"


def verify_doi(doi, expected_title, settings):
    """Same check as check_doi, as (True/False, short reason). This is our defence against AI "inventing" references."""
    state, reason = check_doi(doi, expected_title, settings)
    return state == "match", reason
