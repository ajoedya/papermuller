"""OpenAlex and Crossref lookups that survive a bad moment. Run: python -m unittest discover -s tests -v"""
import csv
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import stages
import tools

LIVE = {'DEMO_MODE': False, 'EMAIL': '', 'FROM_YEAR': 2015, 'TO_YEAR': 2026, 'CANDIDATES': 30}


class Reply:
    def __init__(self, raw=b'{"ok": true}'):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


def http_error(code, headers=None, body=b'{"error": "x"}'):
    return urllib.error.HTTPError('https://api.example', code, 'msg', headers or {}, io.BytesIO(body))


class FetchTests(unittest.TestCase):
    def fetch(self, responses):
        requests = []

        def fake(request, timeout=0):
            requests.append(request)
            result = responses[len(requests) - 1]
            if isinstance(result, Exception):
                raise result
            return result
        with patch('urllib.request.urlopen', side_effect=fake), patch('time.sleep') as sleeping:
            result = tools._fetch('https://api.example/x')
        return result, requests, [c.args[0] for c in sleeping.call_args_list]

    def test_a_good_answer_is_returned_at_once_and_the_service_is_told_who_asks(self):
        result, requests, sleeps = self.fetch([Reply()])
        self.assertEqual((result, sleeps), (('ok', {'ok': True}), []))
        self.assertIn('Papermuller', requests[0].get_header('User-agent'))

    def test_a_404_means_not_found_and_is_never_retried(self):
        result, requests, sleeps = self.fetch([http_error(404)])
        self.assertEqual((result, len(requests), sleeps), (('not_found', None), 1, []))

    def test_temporary_server_problems_are_retried_with_a_pause(self):
        result, requests, sleeps = self.fetch([http_error(500), http_error(503), Reply()])
        self.assertEqual((result, len(requests), sleeps), (('ok', {'ok': True}), 3, [2, 6]))

    def test_a_rate_limit_waits_as_long_as_the_server_asks_but_never_more_than_30_seconds(self):
        self.assertEqual(self.fetch([http_error(429, {'Retry-After': '5'}), Reply()])[2], [5])
        self.assertEqual(self.fetch([http_error(429, {'Retry-After': '9999'}), Reply()])[2], [30])
        self.assertEqual(self.fetch([http_error(429, {'Retry-After': 'soon'}), Reply()])[2], [2])

    def test_it_gives_up_after_three_attempts_with_a_reason(self):
        result, requests, sleeps = self.fetch([http_error(502)] * 3)
        self.assertEqual((result[0], len(requests), sleeps), ('error', 3, [2, 6]))
        self.assertIn('502', result[1])

    def test_refusals_are_not_retried(self):
        for code in (401, 403, 400):
            result, requests, sleeps = self.fetch([http_error(code)])
            self.assertEqual((result[0], len(requests), sleeps), ('error', 1, []), code)

    def test_a_broken_connection_or_a_cut_off_answer_is_retried(self):
        for failure in (urllib.error.URLError('no route'), TimeoutError('slow'), ConnectionResetError(10054, 'reset'),
                        http.client.IncompleteRead(b'part'), http.client.RemoteDisconnected('closed'),
                        Reply(b'{"cut": '), Reply(b'\xff\xfe'), Reply(ConnectionResetError('reset while reading'))):
            result, requests, _ = self.fetch([failure, Reply()])
            self.assertEqual((result, len(requests)), (('ok', {'ok': True}), 2), repr(failure))

    def test_an_error_text_that_cannot_be_read_does_not_crash(self):
        class Broken(io.BytesIO):
            def read(self, *args):
                raise ConnectionResetError('reset')
        result, _, _ = self.fetch([urllib.error.HTTPError('u', 401, 'm', {}, Broken())])
        self.assertEqual(result[0], 'error')

    def test_the_old_helper_still_returns_data_or_none(self):
        with patch('tools._fetch', return_value=('ok', {'a': 1})):
            self.assertEqual(tools._get_json('u'), {'a': 1})
        with patch('tools._fetch', return_value=('error', 'x')):
            self.assertIsNone(tools._get_json('u'))


class CheckDoiTests(unittest.TestCase):
    MESSAGE = {'message': {'DOI': '10.1/abc', 'title': ['Road infrastructure and rural poverty']}}

    def check(self, fetched, settings=LIVE, doi='10.1/ABC'):
        with patch('tools._fetch', return_value=fetched) as fetch, patch('time.sleep'):
            return tools.check_doi(doi, 'Road infrastructure and rural poverty', settings), fetch

    def test_the_four_answers_crossref_can_give(self):
        self.assertEqual(self.check(('ok', self.MESSAGE))[0][0], 'match')
        self.assertEqual(self.check(('ok', {'message': {'DOI': '10.1/abc', 'title': ['A different title']}}))[0][0], 'mismatch')
        self.assertEqual(self.check(('not_found', None))[0], ('not_found', 'DOI not found in Crossref'))
        self.assertEqual(self.check(('ok', None))[0][0], 'not_found')

    def test_a_service_that_did_not_answer_is_unreachable_never_not_found(self):
        (state, reason), _ = self.check(('error', 'server said 503'))
        self.assertEqual(state, 'unreachable')
        self.assertIn('does not mean the DOI is invalid', reason)

    def test_an_invalid_doi_is_rejected_without_asking(self):
        (state, _), fetch = self.check(('ok', self.MESSAGE), doi='not-a-doi')
        self.assertEqual(state, 'invalid')
        fetch.assert_not_called()

    def test_the_email_is_sent_so_crossref_can_use_its_polite_pool(self):
        _, fetch = self.check(('ok', self.MESSAGE), dict(LIVE, EMAIL='me@example.org'))
        self.assertIn('mailto=me%40example.org', fetch.call_args.args[0])
        _, fetch = self.check(('ok', self.MESSAGE))
        self.assertNotIn('mailto', fetch.call_args.args[0])

    def test_verify_doi_keeps_its_old_shape(self):
        with patch('tools._fetch', return_value=('ok', self.MESSAGE)), patch('time.sleep'):
            self.assertEqual(tools.verify_doi('10.1/abc', 'Road infrastructure and rural poverty', LIVE)[0], True)
        with patch('tools._fetch', return_value=('error', 'x')), patch('time.sleep'):
            ok, reason = tools.verify_doi('10.1/abc', 't', LIVE)
        self.assertFalse(ok)
        self.assertIn('could not be reached', reason)

    def test_demo_mode_never_goes_online(self):
        with patch('tools._fetch') as fetch:
            self.assertEqual(tools.check_doi('10.0000/demo.1', 't', {'DEMO_MODE': True})[0], 'match')
            self.assertEqual(tools.check_doi('10.0000/demo.7', 't', {'DEMO_MODE': True})[0], 'not_found')
        fetch.assert_not_called()


class SearchTests(unittest.TestCase):
    def test_strict_search_raises_when_the_service_is_down_and_plain_search_returns_nothing(self):
        with patch('tools._fetch', return_value=('error', 'server said 503')):
            with self.assertRaises(tools.LookupFailed):
                tools.search_papers('roads', LIVE, strict=True)
            self.assertEqual(tools.search_papers('roads', LIVE), [])

    def test_a_real_answer_is_parsed(self):
        data = {'results': [{'title': 'T', 'publication_year': 2020, 'doi': 'https://doi.org/10.1/X',
                             'authorships': [{'author': {'display_name': 'A'}}], 'cited_by_count': 3,
                             'abstract_inverted_index': {'Hello': [0], 'world': [1]}}]}
        with patch('tools._fetch', return_value=('ok', data)), patch('time.sleep'):
            papers = tools.search_papers('roads', LIVE, strict=True)
        self.assertEqual((papers[0]['doi'], papers[0]['abstract']), ('10.1/x', 'Hello world'))


PLAN = {'keywords': ['a', 'b', 'c']}


def paper(number, abstract='abstract'):
    return {'id': f'P{number}', 'doi': f'10.1/{number}', 'title': f'Title {number}', 'abstract': abstract,
            'year': 2020, 'cited_by': 1, 'authors': 'A'}


class StageSearchTests(unittest.TestCase):
    def search(self, outcomes):
        def fake(keyword, settings, how_many=8, strict=False):
            outcome = outcomes[keyword]
            if outcome is None:
                raise tools.LookupFailed(f'OpenAlex could not be reached for {keyword}')
            return outcome
        with patch('stages.search_papers', side_effect=fake), tempfile.TemporaryDirectory() as folder:
            return stages.stage_search(PLAN, LIVE, Path(folder))

    def test_nothing_reached_stops_with_a_message_instead_of_a_misleading_empty_search(self):
        with self.assertRaises(SystemExit) as stop:
            self.search({'a': None, 'b': None, 'c': None})
        self.assertIn('could not be reached for any search term', str(stop.exception))
        self.assertIn('Continue', str(stop.exception))

    def test_one_missing_term_is_skipped_with_a_warning(self):
        papers = self.search({'a': [dict(paper(1), doi='10.1/1')], 'b': None, 'c': [dict(paper(2), doi='10.1/2')]})
        self.assertEqual(len(papers), 2)

    def test_a_search_without_results_is_still_just_empty(self):
        self.assertEqual(self.search({'a': [], 'b': [], 'c': []}), [])


class StageVerifyTests(unittest.TestCase):
    def verify(self, outcomes):
        """outcomes maps a paper id to the list of states Crossref gives on each try."""
        calls = {pid: 0 for pid in outcomes}

        def fake(doi, title, settings):
            pid = 'P' + doi.split('/')[-1]
            state = outcomes[pid][min(calls[pid], len(outcomes[pid]) - 1)]
            calls[pid] += 1
            return state, ('Crossref could not be reached (test)' if state == 'unreachable' else state)
        papers = [paper(int(pid[1:])) for pid in outcomes]
        with patch('stages.check_doi', side_effect=fake), patch('stages.time.sleep') as sleeping, \
                tempfile.TemporaryDirectory() as folder:
            try:
                result = stages.stage_verify(papers, LIVE, Path(folder))
            except SystemExit as stop:
                result = stop
            report = Path(folder, '3_verification_report.csv')
            rows = []
            if report.exists():
                with open(report, encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.DictReader(stream))
        return result, papers, calls, sleeping, rows

    def test_everything_matching_is_verified_without_pausing(self):
        result, _, calls, sleeping, _ = self.verify({f'P{i}': ['match'] for i in range(1, 5)})
        self.assertEqual(len(result), 4)
        sleeping.assert_not_called()

    def test_not_found_and_mismatch_are_final_and_asked_only_once(self):
        result, papers, calls, sleeping, _ = self.verify({'P1': ['match'], 'P2': ['not_found'], 'P3': ['mismatch'], 'P4': ['invalid']})
        self.assertEqual([p['id'] for p in result], ['P1'])
        self.assertEqual(calls, {'P1': 1, 'P2': 1, 'P3': 1, 'P4': 1})
        self.assertEqual({p['id']: p['verified'] for p in papers}, {'P1': 'yes', 'P2': 'no', 'P3': 'no', 'P4': 'no'})
        sleeping.assert_not_called()

    def test_an_article_crossref_missed_once_gets_a_second_chance_after_a_pause(self):
        result, _, calls, sleeping, _ = self.verify({'P1': ['match'], 'P2': ['unreachable', 'match'], 'P3': ['match'],
                                                     'P4': ['match'], 'P5': ['match'], 'P6': ['match']})
        self.assertIn('P2', [p['id'] for p in result])
        self.assertEqual(calls['P2'], 2)
        sleeping.assert_called_once_with(15)

    def test_a_few_unchecked_articles_are_left_out_and_labelled_unchecked_not_no(self):
        result, papers, _, _, rows = self.verify({f'P{i}': ['match'] for i in range(1, 7)} | {'P6': ['unreachable']})
        self.assertNotIn('P6', [p['id'] for p in result])
        self.assertEqual(next(p for p in papers if p['id'] == 'P6')['verified'], 'unchecked')
        self.assertEqual(next(r for r in rows if r['id'] == 'P6')['verified'], 'unchecked')
        self.assertIn('could not be reached', next(r for r in rows if r['id'] == 'P6')['check_note'])

    def test_when_crossref_is_mostly_unreachable_the_stage_stops_so_it_can_be_continued(self):
        outcomes = {f'P{i}': ['match'] for i in range(1, 7)}
        outcomes.update({'P1': ['unreachable'], 'P2': ['unreachable'], 'P3': ['unreachable']})
        result, _, _, _, rows = self.verify(outcomes)
        self.assertIsInstance(result, SystemExit)
        self.assertIn('could not be reached for 3 of 6 articles', str(result))
        self.assertIn('does not mean they are invalid', str(result))
        self.assertIn('Continue', str(result))
        self.assertEqual(len(rows), 6)            # the report is saved even when the stage stops

    def test_a_stopped_verification_is_not_saved_as_finished(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('stages.check_doi', return_value=('unreachable', 'x')), patch('stages.time.sleep'):
            resume = stages.Resume(folder, {'keywords': ['k']}, LIVE, lambda _x: None)
            with self.assertRaises(SystemExit):
                resume.step('verify', lambda: stages.stage_verify([paper(i) for i in range(1, 5)], LIVE, Path(folder)))
            self.assertFalse((Path(folder) / '_checkpoints' / 'verify.json').exists())


if __name__ == '__main__':
    unittest.main()
