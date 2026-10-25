import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from pathlib import Path
from unittest.mock import patch

import app
import pipeline
import llm

class PipelineTests(unittest.TestCase):
    def test_model_roles_and_demo_are_honest(self):
        settings={'DEMO_MODE':False,'MODEL':'provider/general','WRITER_MODEL':'provider/writer',
                  'REVIEW_MODEL':'provider/reviewer','VERIFIER_MODEL':'provider/verifier',
                  'EVIDENCE_MODEL':'provider/evidence'}
        desc=pipeline.describe(settings)
        self.assertEqual(len(desc),10)
        self.assertEqual(desc[4]['model'],'provider/evidence')
        self.assertEqual(desc[6]['model'],'provider/writer')
        self.assertEqual(desc[7]['model'],'provider/verifier')
        self.assertEqual(desc[8]['model'],'provider/reviewer')
        self.assertEqual(pipeline.model_for_role('writer',{'DEMO_MODE':True,'MODEL':'private/model'}),'Demo simulator (offline)')
    def test_llm_model_routing_and_provider_usage_events(self):
        observed=[]
        old_hook=llm.EVENT_HOOK
        try:
            llm.EVENT_HOOK=observed.append
            with patch.object(llm,'_send', return_value='sample') as send:
                self.assertEqual(llm.ask('sample',{'DEMO_MODE':False,'MODEL':'default',
                             'WRITER_MODEL':'writer-only','OPENROUTER_API_KEY':'key'},stage='draft'),'sample')
                self.assertEqual(send.call_args.args[0]['model'],'writer-only')
        finally:
            llm.EVENT_HOOK=old_hook
        # No fabricated usage in demo mode.
        with patch('demo_data.fake_llm_answer',return_value='demo'):
            llm.EVENT_HOOK=observed.append
            try:
                self.assertEqual(llm.ask('x',{'DEMO_MODE':True},stage='plan'),'demo')
            finally:
                llm.EVENT_HOOK=old_hook
        self.assertTrue(observed[-1]['simulated'])
        self.assertEqual(observed[-1]['usage'],{})
    def test_interface_stays_english_with_indonesian_drafts(self):
        # Output-language preferences must not change application navigation or errors.
        from urllib.error import HTTPError
        from urllib.request import Request
        settings = {'DEMO_MODE': True, 'LANGUAGE': 'Indonesian'}
        with patch.object(app, 'read_settings', return_value=(settings, '')):
            with ThreadingHTTPServer(('127.0.0.1', 0), app.Handler) as server:
                old_port = app.PORT
                app.PORT = server.server_address[1]
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f'http://127.0.0.1:{app.PORT}'
                    with urlopen(base + '/') as response:
                        html = response.read().decode()
                    self.assertIn('<html lang="en">', html)
                    self.assertIn('Create research plan', html)
                    with urlopen(base + '/api/status') as response:
                        status = json.load(response)
                    self.assertEqual(status['pipeline'][0]['name'], 'Research plan')
                    request = Request(base + '/api/plan', data=b'{"topic":""}',
                                      headers={'Content-Type': 'application/json'})
                    with self.assertRaises(HTTPError) as failed:
                        urlopen(request)
                    self.assertEqual(failed.exception.code, 400)
                    self.assertEqual(json.load(failed.exception)['error'], 'Enter a research topic.')
                finally:
                    server.shutdown()
                    thread.join()
                    app.PORT = old_port

    def test_events_and_web_status(self):
        old_state=dict(app.STATE)
        try:
            app.STATE.update({'phase':'running','stage':1,'completed_steps':[],'events':[],
                              'usage_by_stage':{},'active_model':'','stage_started':''})
            app.enter_step(2)
            app.on_llm_event({'stage':'draft','model':'actual/openrouter/model','usage':{'prompt_tokens':13,'completion_tokens':8,'total_tokens':21,'cost':0.0001}})
            self.assertIn(1,app.STATE['completed_steps'])
            self.assertEqual(app.STATE['usage_by_stage']['7']['total_tokens'],21)
            self.assertEqual(app.STATE['usage_by_stage']['7']['cost'],0.0001)
            with ThreadingHTTPServer(('127.0.0.1',0),app.Handler) as server:
                port=app.PORT
                app.PORT=server.server_address[1]
                thread=threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                try:
                    with urlopen(f'http://127.0.0.1:{app.PORT}/api/status') as response:
                        body=json.load(response)
                    self.assertEqual(len(body['pipeline']),10)
                    self.assertEqual(body['events'][-1]['model'],'actual/openrouter/model')
                finally:
                    server.shutdown();thread.join();app.PORT=port
        finally:
            app.STATE.clear();app.STATE.update(old_state)

if __name__=='__main__':unittest.main()
