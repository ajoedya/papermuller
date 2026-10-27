"""Local, read-only editorial diagnostics and portable research outputs.

Inspired by MenulisCep4t's document doctor, writing checks and bundles.
This is an original implementation; findings are suggestions, never AI detection.
"""
import io
import json
import re
import zipfile
from pathlib import Path

from quality import paragraph_ids
import writing

RULES = [
    ('generic-opening', r'\bin (?:today[’\x27]s|the modern|the digital) (?:world|era|landscape)\b',
     'Start with the specific research problem instead of a generic opening.'),
    ('chat-residue', r'\b(?:certainly|great question)!|\b(?:i hope this helps|let me know if you)\b',
     'Remove conversational text from the manuscript.'),
    ('inflated-language', r'\b(?:groundbreaking|revolutionary|game-changing|unparalleled)\b',
     'Replace promotional wording with a specific, supported description.'),
    ('claim-strength', r'\b(?:proves? that|conclusively demonstrates?|membuktikan bahwa)\b',
     'Check whether the evidence supports this level of certainty; retain appropriate hedging.'),
    ('generic-opening-id', r'\bdi era (?:digital|modern|globalisasi)\b',
     'Start with the concrete research problem.'),
    ('inflated-language-id', r'\b(?:sangat signifikan|tidak dapat dipungkiri)\b',
     'State the evidence or statistical result rather than adding emphasis.'),
]


def prose(text, protect_quotes=True, reference_labels=()):
    """Mask protected material without moving source line numbers."""
    blank = lambda m: re.sub(r'[^\n]', ' ', m.group())
    text = re.sub(r'^(`{3,}|~{3,})[^\n]*\n.*?^\1[^\n]*(?:\n|$)', blank, text, flags=re.M | re.S)
    text = re.sub(r'`[^`\n]+`|<!--.*?-->|https?://[^\s<>]+', blank, text, flags=re.S)
    if protect_quotes:
        text = re.sub(r'^\s*>.*$', blank, text, flags=re.M)
    text = re.sub(r'^#{1,6}\s+(?:\d+\.?\s+)?(?:' + '|'.join(re.escape(value) for value in {labels[-1] for labels in writing.LABELS.values()} | set(reference_labels)) + r'|bibliography)\s*$.*',
                  blank, text, flags=re.M | re.S | re.I)
    return re.sub(r'"[^"\n]*"|“[^”\n]*”', blank, text) if protect_quotes else text


def inspect_manuscript(text, matrix, filename='manuscript.md', language='English', section_labels=None):
    references = (writing.labels(language, section_labels)['references'],)
    clean = prose(text, reference_labels=references)
    structural = prose(text, protect_quotes=False, reference_labels=references)
    findings = []
    def add(rule, start, excerpt, suggestion, category='style'):
        findings.append(dict(rule=rule, category=category, line=text.count('\n', 0, start) + 1,
                             excerpt=excerpt[:180], suggestion=suggestion))
    for rule, pattern, suggestion in RULES:
        if rule.endswith('-id') and writing.family(language) != 'id':
            continue
        if rule in {'generic-opening', 'inflated-language'} and writing.family(language) != 'en':
            continue
        for match in re.finditer(pattern, clean, re.I):
            add(rule, match.start(), match.group(), suggestion)
    headings = list(re.finditer(r'^(#{1,6})\s+(.+)$', structural, re.M))
    for previous, current in zip(headings, headings[1:]):
        if len(current[1]) > len(previous[1]) + 1:
            add('heading-level', current.start(), current[0], 'Avoid skipping a heading level.', 'structure')
    for match in re.finditer(r'\[(?:AUTHOR TO (?:COMPLETE|WRITE)|PERLU DATA)[^\]]*\]', structural, re.I):
        add('missing-author-content', match.start(), match.group(), 'Complete this section using actual author data.', 'completeness')
    allowed = {str(row['id']).upper() for row in matrix}
    used = set(paragraph_ids(structural))
    for match in re.finditer(r'\[\s*(P\d+(?:\s*[,;]\s*P\d+)*)\s*\]', structural, re.I):
        unknown = set(paragraph_ids(match.group())) - allowed
        if unknown:
            add('unknown-citation', match.start(), match.group(),
                'Check unknown source IDs: ' + ', '.join(sorted(unknown)), 'citation')
    findings.sort(key=lambda item: (item['line'], item['rule']))
    length, unit = writing.length_measure(clean)
    return dict(filename=filename, language=language,
                note='Review suggestions only. These checks do not identify AI authorship or verify scientific accuracy. No text was changed.',
                stats=dict(words=length if unit == 'words' else 0, prose_length=length, length_unit=unit, headings=len(headings),
                           cited_sources=len(used & allowed), available_sources=len(allowed)),
                uncited_sources=sorted(allowed - used), findings=findings)


def bibtex(matrix):
    """Export only known metadata; never invent journal, volume or full author lists."""
    def escape(value):
        replacements = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%',
                        '&': r'\&', '_': r'\_', '#': r'\#', '$': r'\$'}
        return ''.join(replacements.get(c, c) for c in str(value).replace('\n', ' ').replace('\r', ' '))
    entries, seen = [], set()
    for row in matrix:
        key = str(row['id']).upper()
        if not re.fullmatch(r'P\d+', key) or key in seen:
            raise ValueError('BibTeX source IDs must be unique P-number identifiers.')
        seen.add(key)
        fields = [('title', row.get('title', '')), ('year', row.get('year', '')), ('doi', row.get('doi', ''))]
        # Discovery supplies a truncated display string, not structured author metadata.
        fields.append(('note', 'Author display (may be incomplete): ' + str(row.get('authors', ''))))
        entries.append('@misc{' + key + ',\n' + ',\n'.join(
            '  ' + name + ' = {' + escape(value) + '}' for name, value in fields if value) + '\n}')
    return '% Metadata export; check author lists and publication details before submission.\n\n' + '\n\n'.join(entries) + '\n'


def save_outputs(folder, matrix, language='English'):
    folder = Path(folder)
    target = next((folder / name for name in ('9_paper_final.md', '9_paper_draft.md', '7_final_draft.md')
                   if (folder / name).is_file()), None)
    if target:
        sections_file = folder / '9_paper_sections.json'
        saved = json.loads(sections_file.read_text(encoding='utf-8')).get('sections', {}) if sections_file.exists() else {}
        report = inspect_manuscript(target.read_text(encoding='utf-8'), matrix, target.name, language, saved.get('section_labels'))
        (folder / '9_editorial_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / '9_references.bib').write_text(bibtex(matrix), encoding='utf-8')


def research_bundle(folder):
    """Build a current archive of numbered outputs only, excluding symlinks and secrets."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(folder).iterdir()):
            if (path.is_file() and not path.is_symlink()
                    and re.fullmatch(r'0_brainstorm\.json|[1-9]_[a-z0-9_]+\.(?:md|csv|json|docx|bib)', path.name)):
                archive.write(path, arcname=path.name)
    return buffer.getvalue()
