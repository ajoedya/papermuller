"""Dropped connections and failing revision rounds. Run: python -m unittest discover -s tests -v"""
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import llm
import stages

SETTINGS = {'DEMO_MODE': False, 'OPENROUTER_API_KEY': 'key', 'MODEL': 'vendor/a'}
DEMO = {'DEMO_MODE': True, 'MAX_PAPERS': 12, 'MIN_VERIFIED': 5, 'REVISION_ROUNDS': 3,
        'TARGET_SCORE': 8, 'LANGUAGE': 'English', 'CANDIDATES': 30}


class Reply:
    def __init__(self, raw=None):
        self.raw = raw if raw is not None else json.dumps({'choices': [{'message': {'content': 'fine'}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


class ConnectionTests(unittest.TestCase):
    def ask(self, responses):
        calls = []

        def fake(request, timeout=0):
            calls.append(request)
            result = responses[len(calls) - 1]
            if isinstance(result, Exception):
                raise result
            return result
        with patch('urllib.request.urlopen', side_effect=fake), patch('time.sleep') as sleeping:
            try:
                return llm.ask('hello', SETTINGS, stage='draft'), len(calls), sleeping
            except SystemExit as stop:
                return stop, len(calls), sleeping

    def test_a_reset_connection_is_retried_after_a_pause(self):
        reset = ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host')
        result, calls, sleeping = self.ask([reset, Reply()])
        self.assertEqual((result, calls), ('fine', 2))
        sleeping.assert_called_once_with(20)

    def test_other_dropped_connection_kinds_are_retried_too(self):
        for failure in (TimeoutError('timed out'), urllib.error.URLError('dns failure'),
                        http.client.RemoteDisconnected('closed'), http.client.IncompleteRead(b'part'),
                        ConnectionAbortedError('aborted')):
            result, calls, _ = self.ask([failure, Reply()])
            self.assertEqual((result, calls), ('fine', 2), type(failure).__name__)

    def test_a_reply_cut_off_in_the_middle_is_retried(self):
        for raw in (b'{"choices": [{"message": {"con', ConnectionResetError('reset while reading'), b'\xff\xfe'):
            result, calls, _ = self.ask([Reply(raw), Reply()])
            self.assertEqual((result, calls), ('fine', 2), repr(raw))

    def test_gives_up_after_three_attempts_with_a_readable_message(self):
        reset = ConnectionResetError(10054, 'forcibly closed')
        result, calls, sleeping = self.ask([reset, reset, reset])
        self.assertIsInstance(result, SystemExit)
        self.assertIn('Connection problem (ConnectionResetError)', str(result))
        self.assertEqual((calls, sleeping.call_count), (3, 2))

    def test_error_text_that_drops_while_being_read_does_not_crash(self):
        class Broken(io.BytesIO):
            def read(self, *args):
                raise ConnectionResetError('reset')
        error = urllib.error.HTTPError('https://openrouter.ai', 503, 'Unavailable', {}, Broken())
        result, calls, _ = self.ask([error, Reply()])
        self.assertEqual((result, calls), ('fine', 2))   # a 503 is retried even without its text


class RoundFailureTests(unittest.TestCase):
    def run_with(self, failing_call, from_attempt):
        original = getattr(stages, failing_call)
        position = {'stage_draft': 5, 'stage_evidence_audit': 5, 'stage_review': 4}[failing_call]  # where "attempt" sits

        def flaky(*args, **kwargs):
            if args[position] >= from_attempt:
                raise SystemExit('\n[AI ERROR] Connection problem (ConnectionResetError): reset\n')
            return original(*args, **kwargs)
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            plan = stages.stage_plan('road infrastructure governance', DEMO, folder)
            with patch(f'stages.{failing_call}', side_effect=flaky):
                try:
                    result = stages.run_research(plan, DEMO, folder, say=lambda _x: None)
                except SystemExit as stop:
                    return stop, folder, None
                return result, folder, (folder / '7_final_draft.md').read_text(encoding='utf-8')

    def test_a_failing_revision_keeps_the_best_earlier_draft(self):
        for call in ('stage_draft', 'stage_evidence_audit'):
            result, folder, draft = self.run_with(call, from_attempt=2)
            self.assertEqual(result['from_round'], 1, call)
            self.assertEqual(result['verdict'], 'revise', call)
            self.assertIn('Connection problem', result['interrupted'])
            self.assertTrue(any('stopped early' in x for x in result['limitations']))
            self.assertIn('PROVISIONAL DRAFT', draft)

    def test_a_failing_review_in_a_later_round_also_keeps_the_best_draft(self):
        result, _, draft = self.run_with('stage_review', from_attempt=2)
        self.assertEqual(result['from_round'], 1)
        self.assertIn('interrupted', result)
        self.assertIn('PROVISIONAL DRAFT', draft)

    def test_a_failure_in_the_first_round_still_stops_the_run(self):
        result, _, _ = self.run_with('stage_draft', from_attempt=1)
        self.assertIsInstance(result, SystemExit)
        self.assertIn('Connection problem', str(result))


if __name__ == '__main__':
    unittest.main()
