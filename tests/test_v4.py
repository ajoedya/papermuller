import csv
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app
import manuscript
import quality
import sources


def sample_pdf():
    # Production extracts PDFs with pypdf; reportlab only creates the test fixture.
    from reportlab.pdfgen import canvas
    stream = io.BytesIO()
    doc = canvas.Canvas(stream)
    doc.drawString(75, 710, 'Page one discusses financial management methodology and government controls.')
    doc.drawString(75, 690, 'This PDF includes a full-text discussion of local fiscal governance practices.')
    doc.showPage()
    doc.drawString(75, 710, 'Page two explains the evidence: stronger oversight limits unnecessary expenditures.')
    doc.drawString(75, 690, 'The study compares regions with different public procurement rules.')
    doc.showPage()
    doc.save()
    return stream.getvalue()


class FullTextTests(unittest.TestCase):
    def test_import_and_page_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = sources.import_pdf(tmp, 'https://doi.org/10.1234/abc', 'evidence.pdf', sample_pdf())
            self.assertEqual(doc['pages'], 2)
            self.assertEqual(len(sources.list_pdfs(tmp)), 1)
            src = sources.source_for_paper({'id':'P1', 'doi':'10.1234/abc', 'abstract':'different'}, {'PDF_LIBRARY':tmp})
            self.assertEqual(src['source_type'], 'full_text_pdf')
            phrase = 'Page two explains the evidence: stronger oversight limits unnecessary expenditures.'
            self.assertEqual(sources.quote_location(src, phrase, requested_page=2), 2)
            self.assertIsNone(sources.quote_location(src, phrase, requested_page=1))
            cite = quality.citation_audit('The oversight findings are reported in the selected study [P1].', [{'id':'P1'}])
            bad = {'items':[{'paragraph':1,'status':'supported', 'evidence':[{'id':'P1','page':1,'quote':phrase}]}]}
            self.assertFalse(quality.validate_evidence_audit(bad,cite,[{'id':'P1','abstract':'different'}],{'P1':src})['passed'])
            bad['items'][0]['evidence'][0]['page'] = 2
            good = quality.validate_evidence_audit(bad,cite,[{'id':'P1','abstract':'different'}],{'P1':src})
            self.assertTrue(good['passed'])
            self.assertEqual(good['paragraphs'][0]['evidence'][0]['page'], 2)

    def test_http_save_author_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (folder / '4_literature_matrix.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['id','title'])
                writer.writeheader()
                writer.writerow({'id':'P1','title':'Trial'})
            with ThreadingHTTPServer(('127.0.0.1',0), app.Handler) as server:
                old_port, old_state = app.PORT, dict(app.STATE)
                app.PORT = server.server_address[1]
                app.STATE.update({'phase':'done','folder':str(folder)})
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    url = f'http://127.0.0.1:{app.PORT}'
                    body = json.dumps({'papers':{'P1':{'read_full_text':True}},
                                       'checks':{'ai_disclosure_checked':True},
                                       'notes':'I verified the source with the publisher'}).encode()
                    req = Request(url+'/api/verification', body, method='POST',
                                  headers={'Content-Type':'application/json', 'Origin':url})
                    with urlopen(req) as resp:
                        saved = json.load(resp)
                    self.assertEqual(saved['progress']['done'],2)
                    self.assertEqual(json.loads((folder/'8_human_verification.json').read_text())['notes'],
                                     'I verified the source with the publisher')
                finally:
                    server.shutdown()
                    thread.join()
                    app.PORT = old_port
                    app.STATE.clear()
                    app.STATE.update(old_state)

    def test_pdf_validation_and_no_ocr_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                sources.import_pdf(tmp, 'invalid', 'file.pdf', sample_pdf())
            with self.assertRaises(ValueError):
                sources.import_pdf(tmp, '10.1234/a', 'file.pdf', b'not a PDF')

    def test_full_manuscript_does_not_invent_methods(self):
        plan = {'title':'Fiscal governance', 'original_topic':'budget governance', 'scope_note':'No geography chosen',
                'research_questions':['What is known?'], 'author_methods':'', 'author_results':''}
        result, status = manuscript.compile_manuscript(plan, 'Findings discussed [P1].', [], {'passed':True})
        self.assertIn('[PENELITI PERLU MENGISI]', result)
        self.assertNotIn('500 participants', result)
        self.assertEqual(status['results'], 'missing')
        plan['author_results'] = 'Regression output supplied directly by the researcher.'
        edited, status = manuscript.compile_manuscript(plan, 'Findings discussed [P1].', [], {'passed':True})
        self.assertIn(plan['author_results'], edited)
        self.assertEqual(status['results'], 'author_supplied_unverified')

    def test_checklist_cannot_claim_completion_by_default(self):
        matrix = [{'id':'P1'}, {'id':'P2'}]
        blank = manuscript.verification_record(matrix)
        self.assertFalse(manuscript.verified_count(blank)['all_checked'])
        with self.assertRaises(ValueError):
            manuscript.normalize_verification({'papers':{'P999':{}}}, matrix)
        record = manuscript.normalize_verification({'papers':{'P1':{'read_full_text':True}}}, matrix)
        self.assertEqual(manuscript.verified_count(record)['done'], 1)

    def test_http_pdf_import_and_security(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sources, 'library_path', return_value=Path(tmp)):
                with ThreadingHTTPServer(('127.0.0.1', 0), app.Handler) as server:
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    old_port = app.PORT
                    app.PORT = server.server_address[1]
                    thread.start()
                    try:
                        url = f'http://127.0.0.1:{app.PORT}'
                        body = sample_pdf()
                        headers = {'Content-Type':'application/pdf', 'X-Paper-DOI':'10.4321/pdf', 'X-Filename':'read.pdf',
                                   'Origin':url}
                        req = Request(url+'/api/upload-pdf', body, headers=headers, method='POST')
                        with urlopen(req) as response:
                            obj = json.load(response)
                        self.assertEqual(obj['pdf']['pages'], 2)
                        with urlopen(url+'/api/library') as response:
                            found = json.load(response)
                        self.assertEqual(found['pdfs'][0]['doi'], '10.4321/pdf')
                        req = Request(url+'/api/upload-pdf', body, headers={**headers, 'Origin':'https://malicious.example'},method='POST')
                        with self.assertRaises(HTTPError) as denied:
                            urlopen(req)
                        self.assertEqual(denied.exception.code, 403)
                    finally:
                        server.shutdown()
                        thread.join()
                        app.PORT = old_port


class PipelineIntegrationTests(unittest.TestCase):
    def test_matrix_records_pdf_page_provenance(self):
        import stages
        text = 'Page two explains the evidence: stronger oversight limits unnecessary expenditures.'
        p = {'id':'P1', 'title':'Fiscal oversight', 'year':2025, 'authors':'A. Researcher',
             'doi':'10.5432/a', 'abstract':'This abstract describes an investigation.'}
        plan = {'title':'Fiscal oversight', 'research_questions':['How do controls affect spending?'],
                'scope_note':'No location specified.'}
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp)/'library'
            lib.mkdir()
            sources.import_pdf(lib, p['doi'], 'paper.pdf', sample_pdf())
            cfg = {'PDF_LIBRARY':str(lib), 'DEMO_MODE':True}
            fake = {'rows':[{'id':'P1', 'method':'Cross-regional comparison',
                             'main_finding':'Stronger oversight limits unnecessary expenditure',
                             'evidence_quote':text, 'source_page':2,
                             'limitation':'unknown', 'relevance':'Pertinent'}]}
            with patch('stages.ask_for_json', return_value=fake):
                matrix = stages.stage_matrix([p],plan,cfg,Path(tmp))
            self.assertEqual(matrix[0]['quote_verified'],'yes')
            self.assertEqual(matrix[0]['source_type'],'full_text_pdf')
            self.assertEqual(matrix[0]['source_page'],2)
            self.assertEqual(json.loads((Path(tmp)/'4_source_manifest.json').read_text())[0]['type'],'full_text_pdf')
            fake['rows'][0]['source_page'] = 1
            with patch('stages.ask_for_json', return_value=fake):
                other = stages.stage_matrix([p],plan,cfg,Path(tmp))
            self.assertEqual(other[0]['quote_verified'],'no')

    def test_high_risk_redteam_prevents_acceptance(self):
        import stages
        settings = {'DEMO_MODE':True, 'MAX_PAPERS':12, 'MIN_VERIFIED':5,
                    'REVISION_ROUNDS':3, 'TARGET_SCORE':8, 'LANGUAGE':'English', 'CANDIDATES':30}
        challenge = {'findings':[{'severity':'high', 'issue':'Potential causal overstatement',
                                  'location':'some passage', 'action':'Reword the causal statement'}]}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plan = stages.stage_plan('road infrastructure governance',settings,folder)
            original = stages.ask_for_json
            with patch('stages.ask_for_json') as mocked:
                def fake(prompt, opts, stage='general'):
                    return challenge if stage=='redteam' else original(prompt,opts,stage)
                mocked.side_effect = fake
                review = stages.run_research(plan,settings,folder,say=lambda x:None)
            self.assertEqual(review['status'],'needs_human_adjudication')
            self.assertEqual(review['verdict'],'revise')
            self.assertTrue((folder/'8_manuscript_working.md').exists())


if __name__ == '__main__':
    unittest.main()
