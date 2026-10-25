"""Local, opt-in full-text PDF library with page-level provenance.

No shadow downloads or paywall bypassing. User-supplied PDFs remain local except
short excerpts included in prompts sent to the configured model provider.
"""
import hashlib
import io
import json
import re
from pathlib import Path

from quality import normalize_doi, normalize_text, quote_is_in_abstract

MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 150
MAX_PAGE_CHARS = 18000
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


def import_pdf(folder, doi, filename, content):
    """Store the file only if its embedded textual content can be read.

    Accept only PDFs supplied by the user. Scans without a text layer need OCR
    elsewhere and are never silently treated as evidence.
    """
    doi = normalize_doi(doi)
    if not re.fullmatch(r'10\.\d{4,9}/[^\s?#]+', doi, re.I):
        raise ValueError('Masukkan DOI lengkap agar PDF tersambung ke artikel yang tepat.')
    if not content.startswith(b'%PDF-') or len(content) > MAX_PDF_BYTES:
        raise ValueError('Berkas harus PDF berukuran maksimal 12 MB.')
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('Pembaca PDF belum terpasang. Jalankan: pip install -r requirements.txt') from exc
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError('PDF terenkripsi tidak dapat diproses; gunakan salinan yang boleh dibaca.')
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError('PDF harus memiliki 1–150 halaman.')
        pages = []
        total = 0
        for i, page in enumerate(reader.pages, 1):
            value = (page.extract_text(extraction_mode='plain') or '').replace('\x00', ' ')
            if len(value) > MAX_PAGE_CHARS:
                value = value[:MAX_PAGE_CHARS]
            total += len(value)
            if total > MAX_TOTAL_CHARS:
                raise ValueError('PDF terlalu panjang untuk batas pemrosesan lokal.')
            pages.append({'page': i, 'text': value})
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'Gagal membaca struktur PDF: {type(exc).__name__}') from exc
    if total < 180:
        raise ValueError('PDF hampir tidak mempunyai lapisan teks. Jalankan OCR dulu lalu unggah kembali.')
    digest = hashlib.sha256(content).hexdigest()
    base = Path(folder)
    base.mkdir(parents=True, exist_ok=True)
    (base / (digest + '.pdf')).write_bytes(content)
    (base / (digest + '.json')).write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
    index = _index(base)
    index[doi] = {'sha256': digest, 'pages': len(pages), 'characters': total,
                  'filename': Path(str(filename).replace('\\', '/')).name[:140]}
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
                    'sha256': item['sha256'], 'pages': json.loads(path.read_text(encoding='utf-8'))}
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
