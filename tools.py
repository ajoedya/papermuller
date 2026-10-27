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

import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from quality import normalize_doi, title_similarity
import time
import urllib.parse
import urllib.request
import urllib.error


class LiteratureServiceError(RuntimeError):
    """A lookup failed; this is not evidence that a DOI or paper does not exist."""
    def __init__(self, service, status=None, reason='unavailable'):
        self.service, self.status, self.reason = service, status, reason
        detail = f'HTTP {status}' if status else reason
        super().__init__(f'{service}: {detail}. The lookup is unavailable; source existence was not determined.')


def _get_json(url):
    """Only a genuine 404 returns None; transient failures get bounded retries."""
    service = urllib.parse.urlsplit(url).hostname or 'Literature service'
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": "Papermuller/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise LiteratureServiceError(service, reason='invalid JSON response')
            return payload
        except urllib.error.HTTPError as error:
            code, retry_after = error.code, error.headers.get('Retry-After', '') if error.headers else ''
            error.close()
            if code == 404:
                return None
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise LiteratureServiceError(service, code) from None
            try:
                delay = max(0, float(retry_after)) if retry_after else 2 ** attempt
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    delay = 2 ** attempt
            if not math.isfinite(delay) or delay > 5:
                raise LiteratureServiceError(service, code, 'retry later') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise LiteratureServiceError(service, reason='connection failed') from None
            delay = 2 ** attempt
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise LiteratureServiceError(service, reason='invalid JSON response') from None
        time.sleep(delay)


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


def open_access_pdf_urls(item):
    """Use only locations explicitly marked open access; never guess publisher URLs."""
    locations = [item.get('best_oa_location'), item.get('primary_location')] + (item.get('locations') or [])
    urls = []
    for location in locations:
        if isinstance(location, dict) and location.get('is_oa') and location.get('pdf_url'):
            url = location['pdf_url']
            if isinstance(url, str) and url.startswith('https://') and url not in urls:
                urls.append(url)
    return urls[:3]


def search_papers(keyword, settings, how_many=8):
    """Search OpenAlex for papers matching `keyword`. Returns a list of paper dictionaries."""
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

    data = _get_json(url)
    if not data:
        print(f"   ! OpenAlex did not answer for '{keyword}'")
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
            "oa_pdf_urls": open_access_pdf_urls(item),
            "publication_date": item.get("publication_date", ""),
        })
    time.sleep(0.5)  # be polite to the free service
    return papers


def verify_doi(doi, expected_title, settings):
    """
    Ask Crossref: does this DOI really exist, and does its title match?
    Returns (True/False, short reason).
    This is our defence against AI "inventing" references.
    """
    if settings["DEMO_MODE"]:
        from demo_data import fake_verify
        return fake_verify(doi)

    doi = normalize_doi(doi)
    if not doi.startswith("10.") or "/" not in doi:
        return False, "invalid DOI format"
    data = _get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""))
    time.sleep(0.3)
    if not data:
        return False, "DOI not found in Crossref"

    message = data.get("message") or {}
    titles = message.get("title") or []
    real_title = titles[0] if titles else ""
    real_doi = normalize_doi(message.get("DOI"))
    similarity = title_similarity(expected_title, real_title)
    if real_doi == doi and similarity >= 0.82:
        return True, f"Crossref DOI + title match ({similarity:.0%}); content not checked"
    return False, f"metadata mismatch (title similarity {similarity:.0%}; Crossref: {real_title[:60]})"
