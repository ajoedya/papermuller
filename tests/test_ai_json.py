"""Reading JSON out of model replies. Run: python -m unittest discover -s tests -v"""
import unittest
from unittest.mock import patch

import llm


class ExtractTests(unittest.TestCase):
    def test_the_usual_ways_a_model_wraps_its_json(self):
        cases = {
            'clean': ('{"a": 1}', {'a': 1}),
            'code fence': ('Sure!\n```json\n{"a": 1, "b": [1, 2]}\n```\nHope this helps', {'a': 1, 'b': [1, 2]}),
            'text after it': ('{"a": 1} Hope this helps {smile}', {'a': 1}),
            'trailing commas': ('{"rows": [{"id": "P1"}, {"id": "P2"},], "n": 2,}', {'rows': [{'id': 'P1'}, {'id': 'P2'}], 'n': 2}),
            'raw line break in a string': ('{"text": "line one\nline two"}', {'text': 'line one\nline two'}),
            'stray braces in front': ('Use {name} as the key. {"a": 1}', {'a': 1}),
            'byte order mark': ('﻿{"a": 1}', {'a': 1}),
            'accents': ('{"judul": "Pengaruh pembayaran nontunai"}', {'judul': 'Pengaruh pembayaran nontunai'}),
        }
        for name, (reply, expected) in cases.items():
            self.assertEqual(llm.extract_json(reply), expected, name)

    def test_a_wrong_structure_that_looks_fine_is_refused_rather_than_returned(self):
        refused = {
            'cut off': '{"rows": [{"id": "P1"}, {"id": "P2"}',
            'outer object broken': '{"rows": [{"id": "P1"} {"id": "P2"}]}',
            'bare list of objects': '[{"a": 1}]',
            'list after prose': 'Here: [\n {"a": 1}, {"a": 2}\n]',
            'empty': '',
            'none': None,
            'prose only': 'Sorry, I cannot help with that.',
            'only a number': '42',
        }
        for name, reply in refused.items():
            self.assertIsNone(llm.extract_json(reply), name)

    def test_an_object_that_holds_a_list_is_still_accepted(self):
        self.assertEqual(llm.extract_json('{"rows": [{"a": 1}]}'), {'rows': [{'a': 1}]})
        self.assertEqual(llm.extract_json('note [1, 2] then {"a": 1}'), {'a': 1})

    def test_a_long_reply_full_of_braces_does_not_hang(self):
        reply = '{x} ' * 5000 + '{"a": 1'
        self.assertIsNone(llm.extract_json(reply))


class AskForJsonTests(unittest.TestCase):
    PROMPT = 'Summarise these papers. ' * 400          # long, like a real evidence prompt

    def run_ask(self, replies):
        sent = []

        def fake(prompt, settings, stage):
            sent.append((prompt, stage))
            return replies[len(sent) - 1]
        with patch('llm.ask', side_effect=fake):
            try:
                return llm.ask_for_json(self.PROMPT, {}, stage='matrix'), sent
            except SystemExit as stop:
                return stop, sent

    def test_a_good_reply_costs_one_request(self):
        result, sent = self.run_ask(['{"a": 1}'])
        self.assertEqual((result, len(sent)), ({'a': 1}, 1))
        self.assertTrue(sent[0][0].endswith('Answer ONLY with valid JSON, no extra text.'))
        self.assertEqual(sent[0][1], 'matrix')

    def test_a_reply_that_is_slightly_broken_is_repaired_with_a_small_request_not_the_whole_prompt(self):
        broken = '{"a": 1 "b": 2}'
        result, sent = self.run_ask([broken, '{"a": 1, "b": 2}'])
        self.assertEqual((result, len(sent)), ({'a': 1, 'b': 2}, 2))
        repair = sent[1][0]
        self.assertIn('PREVIOUS REPLY', repair)
        self.assertIn(broken, repair)
        self.assertNotIn('Summarise these papers', repair)
        self.assertLess(len(repair), len(sent[0][0]) / 10)
        self.assertEqual(sent[1][1], 'matrix')                  # still routed to the same stage model

    def test_a_cut_off_reply_is_asked_for_again_in_full_because_repairing_it_would_invent_the_rest(self):
        result, sent = self.run_ask(['{"rows": [{"id": "P1"}, {"id": "P2"', '{"rows": []}'])
        self.assertEqual((result, len(sent)), ({'rows': []}, 2))
        self.assertEqual(sent[1][0], sent[0][0])

    def test_a_reply_without_json_is_asked_for_again_in_full(self):
        result, sent = self.run_ask(['I am sorry, I cannot do that.', '{"a": 1}'])
        self.assertEqual((result, sent[1][0]), ({'a': 1}, sent[0][0]))

    def test_three_failures_stop_with_the_start_of_the_last_reply(self):
        result, sent = self.run_ask(['{"a" 1}', '{"a" 2}', '{"a" 3} ' + 'x' * 900])
        self.assertIsInstance(result, SystemExit)
        self.assertEqual(len(sent), 3)
        self.assertIn('Expected JSON but got', str(result))
        self.assertIn('{"a" 3}', str(result))
        self.assertLess(len(str(result)), 700)

    def test_the_third_try_goes_back_to_the_original_prompt(self):
        _, sent = self.run_ask(['{"a" 1}', '{"a" 2}', '{"a": 3}'])
        self.assertIn('PREVIOUS REPLY', sent[1][0])
        self.assertEqual(sent[2][0], sent[0][0])

    def test_demo_answers_still_work(self):
        result = llm.ask_for_json('x', {'DEMO_MODE': True, 'LANGUAGE': 'English'}, stage='outline')
        self.assertIn('themes', result)


if __name__ == '__main__':
    unittest.main()
