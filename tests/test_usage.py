"""Token usage per stage and model. Run: python -m unittest discover -s tests -v"""
import csv
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import app


def post(path, payload):
    request = Request(f'http://127.0.0.1:{app.PORT}{path}', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request) as response:
        return json.load(response)


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.old_state = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                          for k, v in app.STATE.items()}
        app.STATE.update({'usage_by_stage': {}, 'usage_detail': {}, 'events': [], 'folder': ''})

    def tearDown(self):
        app.STATE.clear()
        app.STATE.update(self.old_state)

    def event(self, stage, model, **usage):
        app.on_llm_event({'stage': stage, 'model': model, 'usage': usage})

    def rows(self):
        return {(r['stage'], r['model']): r for r in app.usage_rows()}

    def test_input_and_output_are_summed_per_stage_and_model(self):
        self.event('draft', 'vendor/a', prompt_tokens=1000, completion_tokens=400, total_tokens=1400)
        self.event('draft', 'vendor/a', prompt_tokens=500, completion_tokens=100, total_tokens=600)
        self.event('draft', 'vendor/b', prompt_tokens=7, completion_tokens=3, total_tokens=10)
        self.event('review', 'vendor/a', prompt_tokens=20, completion_tokens=5, total_tokens=25)
        rows = self.rows()
        draft = rows[('draft', 'vendor/a')]
        self.assertEqual((draft['calls'], draft['reported'], draft['input_tokens'], draft['output_tokens'],
                          draft['total_tokens']), (2, 2, 1500, 500, 2000))
        self.assertEqual(rows[('draft', 'vendor/b')]['input_tokens'], 7)
        self.assertEqual(rows[('review', 'vendor/a')]['step'], 9)
        self.assertEqual(len(rows), 3)

    def test_cached_reasoning_and_cost_are_recorded_when_given(self):
        self.event('draft', 'vendor/a', prompt_tokens=100, completion_tokens=50, total_tokens=150, cost=0.0021,
                   prompt_tokens_details={'cached_tokens': 60}, completion_tokens_details={'reasoning_tokens': 20})
        row = self.rows()[('draft', 'vendor/a')]
        self.assertEqual((row['cached_tokens'], row['reasoning_tokens'], row['cost'], row['has_cost']),
                         (60, 20, 0.0021, True))

    def test_total_falls_back_to_input_plus_output(self):
        self.event('draft', 'vendor/a', prompt_tokens=30, completion_tokens=12)
        self.assertEqual(self.rows()[('draft', 'vendor/a')]['total_tokens'], 42)

    def test_a_response_without_usage_counts_as_a_call_but_never_as_zero_tokens(self):
        self.event('draft', 'vendor/a', prompt_tokens=10, completion_tokens=5, total_tokens=15)
        self.event('draft', 'vendor/a')
        row = self.rows()[('draft', 'vendor/a')]
        self.assertEqual((row['calls'], row['reported']), (2, 1))
        self.event('screen', 'vendor/a')
        silent = self.rows()[('screen', 'vendor/a')]
        self.assertEqual((silent['calls'], silent['reported'], silent['has_cost']), (1, 0, False))

    def test_junk_numbers_are_ignored(self):
        self.event('draft', 'vendor/a', prompt_tokens=True, completion_tokens=-5, total_tokens='9',
                   cost=float('inf'), prompt_tokens_details={'cached_tokens': 'many'}, completion_tokens_details=7)
        row = self.rows()[('draft', 'vendor/a')]
        self.assertEqual((row['reported'], row['input_tokens'], row['output_tokens'], row['total_tokens'],
                          row['cached_tokens'], row['reasoning_tokens'], row['has_cost']), (0, 0, 0, 0, 0, 0, False))

    def test_rows_follow_the_flow_order_and_stage_check_is_not_counted(self):
        for stage in ('review', 'plan', 'draft', 'redteam'):
            self.event(stage, 'm', prompt_tokens=1, completion_tokens=1, total_tokens=2)
        self.event('check', 'm', prompt_tokens=1, completion_tokens=1, total_tokens=2)
        self.assertEqual([r['stage'] for r in app.usage_rows()], ['plan', 'draft', 'redteam', 'review'])

    def test_the_old_per_stage_totals_still_work(self):
        self.event('draft', 'vendor/a', prompt_tokens=10, completion_tokens=4, total_tokens=14)
        self.event('draft', 'vendor/b', prompt_tokens=1, completion_tokens=1, total_tokens=2)
        stage = app.STATE['usage_by_stage']['7']
        self.assertEqual((stage['calls'], stage['prompt_tokens'], stage['completion_tokens']), (2, 11, 5))

    def test_csv_report_has_blank_cells_for_unreported_and_a_total_row(self):
        self.event('draft', 'vendor/a', prompt_tokens=1000, completion_tokens=400, total_tokens=1400, cost=0.5)
        self.event('review', 'vendor/a', prompt_tokens=20, completion_tokens=5, total_tokens=25)
        self.event('screen', 'vendor/silent')
        with tempfile.TemporaryDirectory() as name:
            app.STATE['folder'] = name
            app.save_usage_report()
            with open(Path(name) / '9_api_usage.csv', encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
        by_stage = {r['stage']: r for r in rows}
        self.assertEqual(list(by_stage), ['screen', 'draft', 'review', 'TOTAL'])
        self.assertEqual(by_stage['screen']['input_tokens'], '')
        self.assertEqual(by_stage['screen']['responses'], '1')
        self.assertEqual(by_stage['draft']['cost_usd'], '0.5')
        self.assertEqual(by_stage['review']['cost_usd'], '')
        total = by_stage['TOTAL']
        self.assertEqual((total['input_tokens'], total['output_tokens'], total['total_tokens'], total['responses'],
                          total['responses_with_usage'], total['cost_usd']), ('1020', '405', '1425', '3', '2', '0.5'))

    def test_no_report_without_usage_or_without_a_folder(self):
        with tempfile.TemporaryDirectory() as name:
            app.STATE['folder'] = name
            app.save_usage_report()
            self.assertFalse((Path(name) / '9_api_usage.csv').exists())
            self.event('draft', 'm', prompt_tokens=1, completion_tokens=1, total_tokens=2)
            app.STATE['folder'] = str(Path(name) / 'missing')
            app.save_usage_report()
            self.assertFalse((Path(name) / 'missing').exists())


class UsageApiTests(unittest.TestCase):
    def setUp(self):
        self.old_state = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                          for k, v in app.STATE.items()}
        self.old_port = app.PORT
        app.STATE.update({'phase': 'idle', 'usage_by_stage': {}, 'usage_detail': {}, 'events': [], 'folder': ''})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        app.PORT = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # A real run would read the live .env, so jobs are replaced by a no-op.
        patcher = patch.object(app, 'run_in_background')
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        app.PORT = self.old_port
        app.STATE.clear()
        app.STATE.update(self.old_state)

    def test_status_lists_usage_rows_in_order(self):
        app.on_llm_event({'stage': 'draft', 'model': 'm', 'usage': {'prompt_tokens': 4, 'completion_tokens': 2}})
        app.on_llm_event({'stage': 'plan', 'model': 'm', 'usage': {}})
        with urlopen(f'http://127.0.0.1:{app.PORT}/api/status') as response:
            rows = json.load(response)['usage_detail']
        self.assertEqual([r['stage'] for r in rows], ['plan', 'draft'])
        self.assertEqual(rows[1]['input_tokens'], 4)

    def test_brainstorming_spend_survives_a_new_plan_but_not_a_reset(self):
        app.on_llm_event({'stage': 'brainstorm', 'model': 'm', 'usage': {'prompt_tokens': 9, 'completion_tokens': 1}})
        app.on_llm_event({'stage': 'plan', 'model': 'm', 'usage': {'prompt_tokens': 5, 'completion_tokens': 1}})
        post('/api/plan', {'topic': 'roads and poverty'})
        self.assertEqual([r['stage'] for r in app.usage_rows()], ['brainstorm'])
        self.assertEqual(app.STATE['usage_by_stage'], {})
        app.STATE['phase'] = 'idle'
        post('/api/reset', {})
        self.assertEqual(app.usage_rows(), [])


if __name__ == '__main__':
    unittest.main()
