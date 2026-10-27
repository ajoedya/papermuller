import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import app
import editorial
import llm
import sources
import tools
from test_fulltext import PAPER
from test_v4 import sample_pdf


class ReliabilityTests(unittest.TestCase):
    def test_only_404_means_missing_and_credentials_are_not_echoed(self):
        for code in (401,403,404,429,500):
            with patch('urllib.request.urlopen',side_effect=HTTPError('https://api.crossref.org/?api_key=private',code,'error',{},None)),patch('tools.time.sleep'):
                if code==404:
                    self.assertIsNone(tools._get_json('https://api.crossref.org/works/test'))
                else:
                    with self.assertRaises(tools.LiteratureServiceError) as error:
                        tools._get_json('https://api.crossref.org/works/test')
                    self.assertNotIn('private',str(error.exception))
                    self.assertEqual(error.exception.status,code)
        with patch('urllib.request.urlopen',side_effect=URLError('failure')),patch('tools.time.sleep'):
            with self.assertRaises(tools.LiteratureServiceError):
                tools.verify_doi('10.1234/example','Title',{'DEMO_MODE':False})

    def test_retry_after_is_honored_with_bounded_wait_or_stops(self):
        error=HTTPError('https://api.example.org',429,'limit',{'Retry-After':'2'},None)
        with patch('urllib.request.urlopen',side_effect=[error,io.BytesIO(b'{"results":[]}')]) as call,patch('tools.time.sleep') as sleep:
            self.assertEqual(tools._get_json('https://api.example.org'),{'results':[]})
            self.assertEqual(call.call_count,2)
            sleep.assert_called_once_with(2)
        with patch('urllib.request.urlopen',side_effect=HTTPError('https://api.example.org',429,'limit',{'Retry-After':'120'},None)),patch('tools.time.sleep') as sleep:
            with self.assertRaises(tools.LiteratureServiceError):
                tools._get_json('https://api.example.org')
            sleep.assert_not_called()

    def test_invalid_json_and_model_responses_are_errors(self):
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'not-json')):
            with self.assertRaises(tools.LiteratureServiceError): tools._get_json('https://api.example.org')
        for payload in ({'choices':[]},{'choices':[{'message':{'content':None}}]},[],{'choices':[{}]}):
            with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(llm._Retry): llm._send({'model':'m'},{'OPENROUTER_API_KEY':'test'})

    def test_unknown_model_is_not_retried_as_transient_failure(self):
        with patch('urllib.request.urlopen',side_effect=HTTPError('https://openrouter.ai',404,'missing',{},io.BytesIO(b'unknown model'))),patch('llm.time.sleep') as sleep:
            with self.assertRaises(SystemExit):
                llm.ask('hello',{'DEMO_MODE':False,'MODEL':'unknown','OPENROUTER_API_KEY':'test'})
            sleep.assert_not_called()

    def test_pdf_text_cache_reuses_unchanged_file_and_invalidates_edits(self):
        with tempfile.TemporaryDirectory() as name:
            sources.import_pdf(name,PAPER['doi'],'test.pdf',sample_pdf())
            config={'PDF_LIBRARY':name}
            first=sources.source_for_paper(PAPER,config)
            text_file=Path(name)/(first['sha256']+'.json')
            sources._cached_pages.cache_clear()
            reads=[]
            original=Path.read_text
            def read(path,*args,**kwargs):
                if path==text_file: reads.append(path)
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',read):
                sources.source_for_paper(PAPER,config)
                sources.source_for_paper(PAPER,config)
                self.assertEqual(len(reads),1)
                pages=[{'page':1,'text':'Updated evidence.'}]
                text_file.write_text(json.dumps(pages))
                source=sources.source_for_paper(PAPER,config)
                self.assertEqual(source['pages'],pages)
                self.assertEqual(len(reads),2)

    def test_results_api_summary_excludes_large_chunk_notes(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name)
            data=[dict(id='P1',total_chunks=20,processed_chunks=20,text_pages=30,total_pages=30,status='full_text_processed',simulated=False,chunks=[{'note':'x'*50000}])]
            (folder/'4_fulltext_reading.json').write_text(json.dumps(data))
            old=dict(app.STATE)
            try:
                app.STATE['folder']=str(folder)
                result=app.read_results()
                self.assertNotIn('chunks',result['fulltext_reading'][0])
                self.assertLess(len(json.dumps(result['fulltext_reading'])),400)
                self.assertIn('chunks',json.loads((folder/'4_fulltext_reading.json').read_text())[0])
            finally: app.STATE.clear();app.STATE.update(old)

    def test_editorial_cjk_counts_and_translated_references(self):
        text='# 摘要\n\n'+'这是研究论文中的实质内容。'*20+' [P1]\n\n## 参考文献\n\nA revolutionary title [P1].'
        report=editorial.inspect_manuscript(text,[{'id':'P1'}],language='Chinese')
        self.assertEqual(report['stats']['length_unit'],'characters')
        self.assertNotIn('revolutionary',editorial.prose(text))
        self.assertEqual(report['findings'],[])
        report=editorial.inspect_manuscript('Body [P1].\n\n## Kaynakça\n\nBook [P2].',[{'id':'P1'},{'id':'P2'}],language='Turkish',section_labels={'references':'Kaynakça'})
        self.assertEqual(report['uncited_sources'],['P2'])


if __name__=='__main__': unittest.main()
