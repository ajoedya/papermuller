"""Models that OpenRouter limits to agent apps. Run: python -m unittest discover -s tests -v"""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import llm

SETTINGS = {'DEMO_MODE': False, 'OPENROUTER_API_KEY': 'key', 'MODEL': 'vendor/a:free'}


def gated_error(model):
    body = {'error': {'message': f'{model} is only available on agentic harnesses. Try plugging it into a coding agent',
                      'code': 403, 'metadata': {'failed_routing_step': 'Gate Free Endpoints by Agentic Harness'}}}
    return urllib.error.HTTPError('https://openrouter.ai', 403, 'Forbidden', {}, io.BytesIO(json.dumps(body).encode()))


class Reply:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({'choices': [{'message': {'content': 'fine'}}]}).encode()


class GatedModelTests(unittest.TestCase):
    def run_ask(self, settings, responses):
        sent = []

        def fake(request, timeout=0):
            sent.append(json.loads(request.data))
            result = responses[len(sent) - 1]
            if isinstance(result, Exception):
                raise result
            return result
        with patch('urllib.request.urlopen', side_effect=fake), patch('time.sleep') as sleeping:
            try:
                return llm.ask('hello', settings, stage='draft'), sent, sleeping
            except SystemExit as stop:
                return stop, sent, sleeping

    def test_a_gated_model_is_dropped_and_the_next_configured_one_is_used(self):
        settings = dict(SETTINGS, MODEL='vendor/a:free, vendor/b')
        result, sent, sleeping = self.run_ask(settings, [gated_error('vendor/a:free'), Reply()])
        self.assertEqual(result, 'fine')
        self.assertEqual(sent[0]['model'], 'vendor/a:free')
        self.assertEqual(sent[0]['models'], ['vendor/a:free', 'vendor/b'])
        self.assertEqual(sent[1]['model'], 'vendor/b')
        self.assertNotIn('models', sent[1])
        sleeping.assert_not_called()

    def test_with_no_backup_the_error_names_the_model_and_says_what_to_do(self):
        result, sent, sleeping = self.run_ask(SETTINGS, [gated_error('vendor/a:free')])
        self.assertIsInstance(result, SystemExit)
        message = str(result)
        self.assertIn('vendor/a:free', message)
        self.assertIn('approved agent apps', message)
        self.assertIn('openrouter/free', message)
        self.assertNotIn('routing_funnel', message)
        self.assertEqual(len(sent), 1)       # not retried
        sleeping.assert_not_called()

    def test_a_model_chosen_by_a_router_stops_instead_of_looping(self):
        settings = dict(SETTINGS, MODEL='openrouter/free')
        result, sent, _ = self.run_ask(settings, [gated_error('vendor/picked:free')] * 3)
        self.assertIsInstance(result, SystemExit)
        self.assertIn('vendor/picked:free', str(result))
        self.assertEqual(len(sent), 1)

    def test_every_backup_gated_lists_all_of_them(self):
        settings = dict(SETTINGS, MODEL='vendor/a:free, vendor/b:free')
        result, sent, _ = self.run_ask(settings, [gated_error('vendor/a:free'), gated_error('vendor/b:free')])
        self.assertIsInstance(result, SystemExit)
        self.assertIn('vendor/a:free, vendor/b:free', str(result))
        self.assertEqual(len(sent), 2)

    def test_other_403_errors_keep_their_original_message(self):
        other = urllib.error.HTTPError('https://openrouter.ai', 403, 'Forbidden', {}, io.BytesIO(b'{"error":"nope"}'))
        result, sent, _ = self.run_ask(SETTINGS, [other])
        self.assertIsInstance(result, SystemExit)
        self.assertIn('nope', str(result))
        self.assertNotIn('agent apps', str(result))


if __name__ == '__main__':
    unittest.main()
