"""The estimate of AI requests shown before a run. Run: python -m unittest discover -s tests -v"""
import contextlib
import io
import itertools
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import app
import llm
import pipeline
import stages

DEMO = {'DEMO_MODE': True, 'LANGUAGE': 'English', 'CANDIDATES': 30, 'TARGET_SCORE': 8}


class FormulaTests(unittest.TestCase):
    def estimate(self, minimum=5, maximum=12, rounds=3):
        return pipeline.estimate_requests({'MIN_VERIFIED': minimum, 'MAX_PAPERS': maximum, 'REVISION_ROUNDS': rounds})

    def test_the_default_settings(self):
        e = self.estimate()
        self.assertEqual((e['min'], e['max']), (10, 26))

    def test_the_parts_add_up_to_the_totals(self):
        e = self.estimate(3, 40, 5)
        self.assertEqual(sum(p['min'] for p in e['parts']), e['min'])
        self.assertEqual(sum(p['max'] for p in e['parts']), e['max'])
        self.assertEqual([p['part'] for p in e['parts']],
                         ['screen', 'evidence', 'outline', 'review_rounds', 'redteam', 'paper_rounds'])

    def test_evidence_is_extracted_four_articles_per_request(self):
        parts = lambda lo, hi: next(p for p in self.estimate(lo, hi)['parts'] if p['part'] == 'evidence')
        self.assertEqual((parts(1, 4)['min'], parts(1, 4)['max']), (1, 1))
        self.assertEqual((parts(5, 5)['min'], parts(5, 5)['max']), (2, 2))
        self.assertEqual((parts(4, 13)['min'], parts(4, 13)['max']), (1, 4))

    def test_more_revision_rounds_raise_only_the_top_of_the_range(self):
        few, many = self.estimate(rounds=0), self.estimate(rounds=6)
        self.assertGreater(many['max'], few['max'])
        self.assertLessEqual(many['min'] - few['min'], 2)       # the fewest barely moves

    def test_odd_settings_never_give_a_negative_or_inverted_range(self):
        for settings in ({}, {'MIN_VERIFIED': 0, 'MAX_PAPERS': 0}, {'MIN_VERIFIED': 9, 'MAX_PAPERS': 2, 'REVISION_ROUNDS': None},
                         {'MIN_VERIFIED': '5', 'MAX_PAPERS': '12', 'REVISION_ROUNDS': '3'}):
            e = pipeline.estimate_requests(settings)
            self.assertTrue(0 < e['min'] <= e['max'], settings)


class AgainstARealRunTests(unittest.TestCase):
    def test_the_range_holds_for_the_number_of_requests_a_demo_run_actually_makes(self):
        for rounds, (fewest, most) in itertools.product((0, 1, 2, 3), ((5, 12), (3, 4), (6, 6))):
            settings = dict(DEMO, REVISION_ROUNDS=rounds, MIN_VERIFIED=fewest, MAX_PAPERS=most)
            counted = []
            old_hook, llm.EVENT_HOOK = llm.EVENT_HOOK, counted.append
            try:
                with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
                    plan = stages.stage_plan('roads and poverty', settings, Path(folder))
                    counted.clear()                       # the plan is already approved when the estimate is shown
                    stages.run_research(plan, settings, Path(folder), say=lambda _x: None)
            finally:
                llm.EVENT_HOOK = old_hook
            e = pipeline.estimate_requests(settings)
            self.assertTrue(e['min'] <= len(counted) <= e['max'],
                            f'rounds={rounds} min={fewest} max={most}: {len(counted)} not in {e["min"]}-{e["max"]}')


class StatusAndPageTests(unittest.TestCase):
    def setUp(self):
        self.old_state, self.old_port = dict(app.STATE), app.PORT
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        app.PORT = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        app.PORT = self.old_port
        app.STATE.clear()
        app.STATE.update(self.old_state)

    def status(self, settings):
        with patch.object(app, 'read_settings', return_value=(settings, '' if settings else 'broken')):
            with urlopen(f'http://127.0.0.1:{app.PORT}/api/status') as response:
                return json.load(response)

    def test_the_status_carries_the_estimate_for_the_current_settings(self):
        body = self.status(dict(DEMO, MIN_VERIFIED=5, MAX_PAPERS=12, REVISION_ROUNDS=3))
        self.assertEqual((body['estimate']['min'], body['estimate']['max']), (10, 26))
        body = self.status(dict(DEMO, MIN_VERIFIED=5, MAX_PAPERS=12, REVISION_ROUNDS=0))
        self.assertEqual((body['estimate']['min'], body['estimate']['max']), (8, 11))

    def test_unreadable_settings_give_no_estimate_instead_of_an_error(self):
        self.assertIsNone(self.status(None)['estimate'])

    def test_the_note_sits_in_the_plan_approval_card_and_both_languages_have_it(self):
        html = Path(__file__).resolve().parents[1].joinpath('ui.html').read_text(encoding='utf-8')
        self.assertLess(html.index('id="approveCard"'), html.index('id="estimateNote"'))
        self.assertLess(html.index('id="estimateNote"'), html.index('id="progressCard"'))
        for key in ('estimateNote', 'estimateUsed', 'estimateDemo'):
            self.assertEqual(html.count(f'{key}:'), 2, key)
        self.assertIn('{a} sampai {b}', html)
        self.assertIn('{a} to {b}', html)


if __name__ == '__main__':
    unittest.main()
