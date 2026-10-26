"""Local full-text PDF library with page-level provenance.

No shadow downloads or paywall bypassing. User-supplied PDFs remain local except
text chunks included in prompts sent to the configured model provider.
"""
import hashlib
import io
import json
import re
from pathlib import Path

from quality import normalize_doi, normalize_text, quote_is_in_abstract

MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 150
MAX_TOTAL_CHARS = 900000


def library_path(settings=None):
    return Path((settings or {}).get('PDF_LIBRARY') or Path(__file__).parent / 'library')


def _index(folder):
    path = Path(folder) / 'index.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def list_pdfs(folder):
    return [{"doi": doi, "sha256": item['sha256'], "pages": item['pages'],
             "characters": item['characters'], "filename": item['filename']}
            for doi, item in sorted(_index(folder).items())]


def extract_pdf(content):
    """Extract every text character within explicit PDF size/page/total limits."""
    if not content.startswith(b'%PDF-') or len(content) > MAX_PDF_BYTES:
        raise ValueError('Choose a PDF no larger than 12 MB.')
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('PDF reader not installed. Run: pip install -r requirements.txt') from exc
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs cannot be processed. Use an accessible copy you have permission to read.')
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError('PDFs must contain 1–150 pages.')
        pages = []
        total = 0
        for i, page in enumerate(reader.pages, 1):
            value = (page.extract_text(extraction_mode='plain') or '').replace('\x00', ' ')
            total += len(value)
            if total > MAX_TOTAL_CHARS:
                raise ValueError('The PDF exceeds the local text processing limit.')
            pages.append({'page': i, 'text': value})
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'Could not read the PDF structure: {type(exc).__name__}') from exc
    if sum(len(p['text'].strip()) for p in pages) < 180:
        raise ValueError('This PDF has too little selectable text. Run OCR before uploading it again.')
    return pages, total


def import_pdf(folder, doi, filename, content, *, expected_paper=None, source_url='', origin='uploaded'):
    """Store readable PDF text. Automatically fetched PDFs must match DOI or title."""
    doi = normalize_doi(doi)
    if not re.fullmatch(r'10\.\d{4,9}/[^\s?#]+', doi, re.I):
        raise ValueError('Enter a complete DOI to link the PDF to its article.')
    pages, total = extract_pdf(content)
    if expected_paper:
        front = ' '.join(p['text'] for p in pages[:2])[:24000]
        title = normalize_text(expected_paper.get('title', ''))
        compact = re.sub(r'\s+', '', front).lower()
        if doi not in compact and (len(title) < 15 or title not in normalize_text(front)):
            raise ValueError('Downloaded PDF identity could not be matched to the selected DOI or title.')
    digest = hashlib.sha256(content).hexdigest()
    base = Path(folder)
    base.mkdir(parents=True, exist_ok=True)
    (base / (digest + '.pdf')).write_bytes(content)
    (base / (digest + '.json')).write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
    index = _index(base)
    index[doi] = {'sha256': digest, 'pages': len(pages), 'characters': total,
                  'filename': Path(str(filename).replace('\\', '/')).name[:140],
                  'origin': origin, 'source_url': source_url}
    (base / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'doi': doi, **index[doi]}


def source_for_paper(paper, settings=None):
    """Always return a source object; known PDF DOI takes precedence over abstract."""
    doi = normalize_doi(paper.get('doi', ''))
    folder = library_path(settings)
    item = _index(folder).get(doi)
    if item:
        path = folder / (item['sha256'] + '.json')
        if path.is_file():
            return {'id': paper['id'], 'source_type': 'full_text_pdf', 'doi': doi,
                    'sha256': item['sha256'], 'pages': json.loads(path.read_text(encoding='utf-8')),
                    'origin': item.get('origin', 'uploaded'), 'source_url': item.get('source_url', '')}
    return {'id': paper['id'], 'source_type': 'abstract_only', 'doi': doi,
            'sha256': '', 'pages': [{'page': 0, 'text': paper.get('abstract', '')}]}


def quote_location(source, quote, requested_page=None):
    """Only accept exact normalized contiguous matches on a documented page."""
    for p in source.get('pages', []):
        if requested_page is not None and requested_page != p['page']:
            continue
        if quote_is_in_abstract(quote, p['text']):
            return p['page']
    return None


def relevant_snippets(source, plan, limit=4):
    """Select limited page-grounded text to manage token costs, not entire PDF."""
    terms = set(re.findall(r'\w{4,}', normalize_text(
        plan.get('title', '') + ' ' + ' '.join(plan.get('research_questions', [])))))
    candidates = []
    for item in source['pages']:
        page = item['page']
        text = re.sub(r'\s+', ' ', item['text']).strip()
        if not text:
            continue
        for start in range(0, len(text), 1400):
            chunk = text[start:start + 1700]
            if len(chunk) < 80:
                continue
            hits = set(re.findall(r'\w{4,}', normalize_text(chunk))) & terms
            candidates.append((len(hits), -start, -page, page, chunk))
    candidates.sort(reverse=True)
    selected = []
    seen = set()
    for _, _, _, page, chunk in candidates:
        identifier = (page, chunk[:60])
        if identifier in seen:
            continue
        selected.append({'page': page, 'text': chunk})
        seen.add(identifier)
        if len(selected) >= limit:
            break
    return selected


def source_prompt(source, plan):
    parts = relevant_snippets(source, plan)
    return '\n'.join(f"[PAGE {p['page'] if p['page'] else 'ABSTRACT'}] {p['text']}" for p in parts)


def full_text_chunks(source, max_chars=16000):
    """Pack ALL extracted text into bounded, page-labelled chunks without truncation."""
    chunks, parts, size = [], [], 0
    for page in source['pages']:
        text = page['text']
        for start in range(0, len(text), max_chars - 80):
            piece = text[start:start + max_chars - 80]
            if not piece.strip():
                continue
            part = {'page': page['page'], 'text': piece, 'offset': start}
            cost = len(piece) + 40
            if parts and size + cost > max_chars:
                chunks.append(parts)
                parts, size = [], 0
            parts.append(part)
            size += cost
    if parts:
        chunks.append(parts)
    return chunks


def audit_source_prompt(source, plan, row=None):
    """Include the extracted evidence page even when lexical ranking misses it."""
    parts = relevant_snippets(source, plan)
    if row and row.get('evidence_quote'):
        page_no = quote_location(source, row['evidence_quote'])
        if page_no is not None:
            page = next(p for p in source['pages'] if p['page'] == page_no)
            normalized = re.sub(r'\s+', ' ', page['text'])
            quote = re.sub(r'\s+', ' ', row['evidence_quote'])
            start = max(0, normalized.casefold().find(quote.casefold()) - 400)
            parts.insert(0, {'page': page_no, 'text': normalized[start:start + max(2200, len(quote) + 800)]})
    return '\n'.join(f"[PAGE {p['page'] if p['page'] else 'ABSTRACT'}] {p['text']}" for p in parts)
