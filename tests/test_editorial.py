import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

import app
import editorial
import stages

MATRIX = [{'id': 'P1', 'title': 'Growth & risk {study}', 'year': 2024,
           'authors': 'A. One, B. Two', 'doi': '10.1234/a_b'}]


class EditorialTests(unittest.TestCase):
    def test_line_locations_protected_quotes_and_claims(self):
        text = ('# Title\n\nIn the modern world, this is revolutionary [P1].\n'
                'The association may depend on context (p = 0.03; n = 400).\n'
                '> The source says revolutionary.\n'
                'A quote: "groundbreaking evidence" [P1].\n'
                '`revolutionary`\n```text\nrevolutionary\n```\n'
                'The findings prove that roads help [P99].\n'
                '## References\n\n- [P1] Revolutionary work.\n')
        report = editorial.inspect_manuscript(text, MATRIX)
        self.assertEqual([f['line'] for f in report['findings'] if f['rule'] == 'inflated-language'], [3])
        self.assertEqual([f['line'] for f in report['findings'] if f['rule'] == 'claim-strength'], [11])
        self.assertEqual([f['excerpt'] for f in report['findings'] if f['rule'] == 'unknown-citation'], ['[P99]'])
        self.assertEqual(report['stats']['cited_sources'], 1)
        self.assertIn('n = 400', text)
        self.assertNotIn('p = 0.03', str(report['findings']))

    def test_missing_author_sections_and_indonesian_rules(self):
        text = '# Paper\n\n### Methods\n\n> **[AUTHOR TO COMPLETE]** Real data required.\nDi era digital, hasil ini sangat signifikan.\n'
        report = editorial.inspect_manuscript(text, MATRIX, language='Indonesian')
        rules = {f['rule'] for f in report['findings']}
        self.assertTrue({'missing-author-content', 'heading-level', 'generic-opening-id', 'inflated-language-id'} <= rules)
        self.assertEqual(report['uncited_sources'], ['P1'])

    def test_metadata_export_does_not_invent_or_accept_injected_keys(self):
        exported = editorial.bibtex(MATRIX)
        self.assertIn('@misc{P1,', exported)
        self.assertIn(r'Growth \& risk \{study\}', exported)
        self.assertIn('may be incomplete', exported)
        self.assertNotIn('journal =', exported)
        self.assertNotIn('\n  author =', exported)
        with self.assertRaises(ValueError):
            editorial.bibtex([dict(MATRIX[0], id='P1}, @article{injected')])

    def test_outputs_preserve_manuscript_and_bundle_is_current_and_scoped(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            draft = '# Paper\n\nA revolutionary effect of 0.4 [P1].'
            (folder / '9_paper_draft.md').write_text(draft)
            (folder / '.env').write_text('SECRET=private')
            (folder / 'log.txt').write_text('private debug detail')
            (folder / '9_external.json').symlink_to(folder / '.env')
            editorial.save_outputs(folder, MATRIX)
            self.assertEqual((folder / '9_paper_draft.md').read_text(), draft)
            self.assertEqual(json.loads((folder / '9_editorial_report.json').read_text())['filename'], '9_paper_draft.md')
            (folder / '9_paper_final.md').write_text('# Final\n\nActual finding [P1].')
            editorial.save_outputs(folder, MATRIX)
            self.assertEqual(json.loads((folder / '9_editorial_report.json').read_text())['filename'], '9_paper_final.md')
            with zipfile.ZipFile(io.BytesIO(editorial.research_bundle(folder))) as archive:
                self.assertIn('9_paper_final.md', archive.namelist())
                self.assertIn('9_references.bib', archive.namelist())
                self.assertNotIn('9_external.json', archive.namelist())
                self.assertNotIn('.env', archive.namelist())
                self.assertNotIn('log.txt', archive.namelist())

    def test_demo_and_http_exports(self):
        settings = dict(DEMO_MODE=True, MAX_PAPERS=12, MIN_VERIFIED=5, REVISION_ROUNDS=3,
                        TARGET_SCORE=8, LANGUAGE='English', CANDIDATES=30)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            folder = root / '20261027_120000'
            folder.mkdir()
            plan = stages.stage_plan('governance and roads', settings, folder)
            stages.run_research(plan, settings, folder, say=lambda _: None)
            report = json.loads((folder / '9_editorial_report.json').read_text())
            self.assertEqual(report['filename'], '9_paper_draft.md')
            old_state = dict(app.STATE)
            try:
                app.STATE.update(phase='done', folder=str(folder))
                with patch.object(app, 'PROJECTS', root):
                    with ThreadingHTTPServer(('127.0.0.1', 0), app.Handler) as server:
                        with patch.object(app, 'PORT', server.server_address[1]):
                            thread = threading.Thread(target=server.serve_forever, daemon=True)
                            thread.start()
                            try:
                                base = f'http://127.0.0.1:{app.PORT}'
                                with urlopen(base + '/api/results') as response:
                                    self.assertEqual(json.load(response)['editorial']['filename'], report['filename'])
                                with urlopen(base + '/files/' + folder.name + '/9_research_bundle.zip') as response:
                                    with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                                        self.assertIn('9_references.bib', archive.namelist())
                                with urlopen(base + '/files/' + folder.name + '/9_references.bib') as response:
                                    self.assertIn('@misc{P1', response.read().decode())
                                with self.assertRaises(HTTPError):
                                    urlopen(base + '/files/20200101_000000/9_research_bundle.zip')
                            finally:
                                server.shutdown()
                                thread.join()
            finally:
                app.STATE.clear()
                app.STATE.update(old_state)


if __name__ == '__main__':
    unittest.main()
