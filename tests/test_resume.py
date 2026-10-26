"""Retrying a stopped run: finished stages are reused and only the failed one is repeated.
Run: python -m unittest discover -s tests -v"""
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
import stages
from stages import Resume

DEMO = {'DEMO_MODE': True, 'MAX_PAPERS': 12, 'MIN_VERIFIED': 5, 'REVISION_ROUNDS': 3,
        'TARGET_SCORE': 8, 'LANGUAGE': 'English', 'CANDIDATES': 30}
PLAN = {'title': 'T', 'research_questions': ['Q?'], 'keywords': ['k'], 'scope_note': 'S', 'original_topic': 'topic'}


class ResumeClassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.said = []

    def resume(self, plan=PLAN, **settings):
        return Resume(self.folder, plan, dict(DEMO, **settings), self.said.append)

    def run_step(self, resume, name='search', extra=None):
        calls = []
        value = resume.step(name, lambda: calls.append(1) or {'rows': [1, 2, 3], 'text': 'ünï'}, extra)
        return value, len(calls)

    def test_a_finished_stage_is_read_back_instead_of_repeated(self):
        self.assertEqual(self.run_step(self.resume())[1], 1)
        value, calls = self.run_step(self.resume())
        self.assertEqual((calls, value), (0, {'rows': [1, 2, 3], 'text': 'ünï'}))
        self.assertTrue(any("Reusing the saved result of 'search'" in x for x in self.said))

    def test_a_different_plan_or_a_dependent_setting_starts_again(self):
        self.run_step(self.resume())
        self.assertEqual(self.run_step(self.resume(dict(PLAN, keywords=['other'])))[1], 1)
        self.assertEqual(self.run_step(self.resume(dict(PLAN, scope_note='wider')))[1], 1)
        for change in ({'CANDIDATES': 10}, {'MAX_PAPERS': 5}, {'FROM_YEAR': 2020}, {'LANGUAGE': 'Indonesian'},
                       {'OPEN_ACCESS_ONLY': True}, {'WORK_TYPE': 'review'}, {'MIN_CITATIONS': 5}, {'TO_YEAR': 2024}):
            self.run_step(self.resume())          # save with the original settings
            self.assertEqual(self.run_step(self.resume(**change))[1], 1, change)

    def test_models_limits_and_thresholds_keep_the_finished_work(self):
        self.run_step(self.resume())
        for change in ({'MODEL': 'vendor/other'}, {'WRITER_MODEL': 'vendor/w'}, {'MIN_VERIFIED': 1},
                       {'REVISION_ROUNDS': 0}, {'TARGET_SCORE': 5}, {'OPENROUTER_API_KEY': 'new'}):
            self.assertEqual(self.run_step(self.resume(**change))[1], 0, change)

    def test_extra_inputs_are_part_of_the_check(self):
        self.run_step(self.resume(), 'paper_draft_1', extra=['author text'])
        self.assertEqual(self.run_step(self.resume(), 'paper_draft_1', extra=['author text'])[1], 0)
        self.assertEqual(self.run_step(self.resume(), 'paper_draft_1', extra=['edited'])[1], 1)

    def test_a_failing_stage_saves_nothing_and_is_tried_again_next_time(self):
        def fail():
            raise SystemExit('boom')
        with self.assertRaises(SystemExit):
            self.resume().step('matrix', fail)
        self.assertFalse((self.folder / '_checkpoints' / 'matrix.json').exists())
        self.assertEqual(self.run_step(self.resume(), 'matrix')[1], 1)

    def test_an_unreadable_saved_file_is_ignored(self):
        self.run_step(self.resume())
        for junk in ('', '{not json', '[]', '{"fingerprint": 1}', 'null'):
            (self.folder / '_checkpoints' / 'search.json').write_text(junk, encoding='utf-8')
            self.assertEqual(self.run_step(self.resume())[1], 1, junk)

    def test_adding_a_pdf_to_the_library_starts_again(self):
        library = self.folder / 'library'
        library.mkdir()
        self.run_step(self.resume(PDF_LIBRARY=str(library)))
        self.assertEqual(self.run_step(self.resume(PDF_LIBRARY=str(library)))[1], 0)
        (library / 'paper.pdf').write_bytes(b'%PDF-1.4')
        self.assertEqual(self.run_step(self.resume(PDF_LIBRARY=str(library)))[1], 1)
        # an empty or missing setting must never scan the current folder
        self.assertEqual(stages.library_signature({'PDF_LIBRARY': ''}), [])
        self.assertEqual(stages.library_signature({'PDF_LIBRARY': str(self.folder / 'missing')}), [])


class Spy:
    """Wraps a stage function to count its calls and optionally make some of them fail."""
    def __init__(self, module, name, fail=lambda number, args: False):
        self.original, self.fail, self.calls = getattr(module, name), fail, []
        self.patcher = patch.object(module, name, side_effect=self)

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if self.fail(len(self.calls), args):
            raise SystemExit('\n[AI ERROR] boom\n')
        return self.original(*args, **kwargs)

    def __enter__(self):
        self.patcher.start()
        return self

    def __exit__(self, *exc):
        self.patcher.stop()


class RunRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.plan = stages.stage_plan('road infrastructure governance', DEMO, self.folder)

    def run_once(self, settings=DEMO):
        return stages.run_research(self.plan, settings, self.folder, say=lambda _x: None)

    def test_a_failure_in_evidence_extraction_keeps_search_checks_and_selection(self):
        with Spy(stages, 'stage_matrix', lambda n, a: True):
            with self.assertRaises(SystemExit):
                self.run_once()
        saved = {p.stem for p in (self.folder / '_checkpoints').glob('*.json')}
        self.assertEqual(saved, {'search', 'verify', 'screen'})
        with Spy(stages, 'stage_search') as search, Spy(stages, 'stage_verify') as verify, \
                Spy(stages, 'stage_screen') as screen, Spy(stages, 'stage_matrix') as matrix, \
                Spy(stages, 'stage_outline') as outline:
            result = self.run_once()
        self.assertEqual([len(x.calls) for x in (search, verify, screen)], [0, 0, 0])
        self.assertEqual([len(matrix.calls), len(outline.calls)], [1, 1])
        self.assertEqual(result['verdict'], 'accept')

    def test_a_failure_in_a_later_revision_continues_from_that_round(self):
        with Spy(stages, 'stage_draft', lambda n, a: a[5] >= 2):
            first = self.run_once()
        self.assertEqual((first['from_round'], first['verdict']), (1, 'revise'))
        self.assertIn('interrupted', first)
        with Spy(stages, 'stage_draft') as draft, Spy(stages, 'stage_evidence_audit') as audit, \
                Spy(stages, 'stage_search') as search, Spy(stages, 'stage_matrix') as matrix:
            result = self.run_once()
        self.assertEqual([a[5] for a in draft.calls], [2, 3, 4])      # round 1 was not written again
        self.assertEqual([a[5] for a in audit.calls], [2, 3, 4])
        self.assertEqual([len(search.calls), len(matrix.calls)], [0, 0])
        self.assertEqual(result['verdict'], 'accept')
        self.assertNotIn('interrupted', result)

    def test_a_failed_full_paper_is_retried_without_repeating_the_literature_review(self):
        with patch('paper.stage_paper_draft', side_effect=SystemExit('\n[AI ERROR] boom\n')):
            first = self.run_once()
        self.assertEqual(first['paper_status'], 'paper_stage_failed')
        with Spy(stages, 'stage_search') as search, Spy(stages, 'stage_draft') as draft, \
                Spy(stages, 'stage_evidence_audit') as audit, Spy(stages, 'stage_review') as review:
            second = self.run_once()
        self.assertEqual([len(x.calls) for x in (search, draft, audit, review)], [0, 0, 0, 0])
        self.assertEqual(second['paper_status'], 'ai_review_passed_awaiting_researcher')

    def test_loosening_a_limit_after_a_too_few_articles_stop_resumes_instead_of_searching_again(self):
        strict = dict(DEMO, MIN_VERIFIED=40, MAX_PAPERS=40)
        with self.assertRaises(SystemExit) as stop:
            self.run_once(strict)
        self.assertIn('Fewer relevant articles', str(stop.exception))
        with Spy(stages, 'stage_search') as search, Spy(stages, 'stage_screen') as screen:
            result = self.run_once(dict(strict, MIN_VERIFIED=5))
        self.assertEqual((len(search.calls), len(screen.calls)), (0, 0))
        self.assertIn(result['verdict'], ('accept', 'revise'))

    def test_changing_the_search_window_redoes_the_search(self):
        with Spy(stages, 'stage_matrix', lambda n, a: True):
            with self.assertRaises(SystemExit):
                self.run_once()
        with Spy(stages, 'stage_search') as search:
            self.run_once(dict(DEMO, FROM_YEAR=2016, TO_YEAR=2026))   # still keeps the demo articles
        self.assertEqual(len(search.calls), 1)

    def test_a_clean_first_run_is_unchanged_by_the_checkpoints(self):
        result = self.run_once()
        self.assertEqual(result['verdict'], 'accept')
        self.assertTrue((self.folder / '_checkpoints' / 'draft_4.json').exists())
        self.assertTrue((self.folder / '9_paper_final.md').exists() or (self.folder / '9_paper_draft.md').exists())


class ResumeApiTests(unittest.TestCase):
    def setUp(self):
        self.old_state = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                          for k, v in app.STATE.items()}
        self.old_port = app.PORT
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        app.STATE.update({'phase': 'failed', 'stage': 7, 'plan': dict(PLAN), 'topic': 'topic', 'folder': self.tmp.name,
                          'error': 'boom', 'completed_steps': [1, 2, 3, 4, 5, 6], 'resumable': False})
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

    def post(self, path, payload=None):
        request = Request(f'http://127.0.0.1:{app.PORT}{path}', data=json.dumps(payload or {}).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_what_continue_would_do_in_each_state(self):
        self.assertEqual(app.resume_kind(), 'run')
        app.STATE['plan'] = None
        self.assertEqual(app.resume_kind(), 'plan')
        app.STATE['topic'] = ''
        self.assertEqual(app.resume_kind(), '')
        app.STATE.update({'phase': 'done', 'plan': dict(PLAN), 'resumable': True})
        self.assertEqual(app.resume_kind(), 'run')
        app.STATE['resumable'] = False
        self.assertEqual(app.resume_kind(), '')
        for phase in ('idle', 'planning', 'approve', 'running'):
            app.STATE.update({'phase': phase, 'resumable': True})
            self.assertEqual(app.resume_kind(), '', phase)
        app.STATE.update({'phase': 'failed', 'folder': str(Path(self.tmp.name) / 'gone')})
        self.assertEqual(app.resume_kind(), 'plan' if not app.STATE['plan'] else '')

    def test_continuing_restarts_the_research_job_and_keeps_finished_steps_marked_done(self):
        with patch.object(app, 'run_in_background') as start:
            status, body = self.post('/api/resume')
        self.assertEqual((status, body['resumed']), (200, 'run'))
        self.assertEqual((app.STATE['phase'], app.STATE['error'], app.STATE['completed_steps']), ('running', '', [1]))
        start.assert_called_once()
        with urlopen(f'http://127.0.0.1:{app.PORT}/api/status') as response:
            self.assertEqual(json.load(response)['resume'], '')    # running: nothing more to continue

    def test_the_continued_job_says_so_and_flags_an_unfinished_step(self):
        for review, flagged in (({'verdict': 'accept'}, False), ({'interrupted': 'boom'}, True),
                                ({'paper_status': 'paper_stage_failed'}, True),
                                ({'status': 'redteam_check_incomplete'}, True)):
            app.STATE.update({'phase': 'running', 'resumable': False})
            with patch.object(app, 'read_settings', return_value=(dict(DEMO), '')), \
                    patch.object(app, 'say') as say, \
                    patch.object(stages, 'run_research', return_value=review) as research:
                app.job_research(dict(PLAN), resumed=True)
            self.assertEqual((app.STATE['phase'], app.STATE['resumable']), ('done', flagged), review)
            research.assert_called_once()
            self.assertIn('finished stages are not run again', say.call_args_list[0].args[0])
        with patch.object(app, 'read_settings', return_value=(dict(DEMO), '')), patch.object(app, 'say') as say, \
                patch.object(stages, 'run_research', return_value={}):
            app.job_research(dict(PLAN))
        self.assertEqual(say.call_args_list[0].args[0], 'Plan approved by the researcher.')

    def test_continuing_a_failed_plan_starts_the_plan_again_for_the_same_topic(self):
        app.STATE['plan'] = None
        with patch.object(app, 'start_plan') as start:
            status, body = self.post('/api/resume')
        self.assertEqual((status, body['resumed']), (200, 'plan'))
        start.assert_called_once_with('topic')

    def test_nothing_to_continue_is_a_clear_conflict(self):
        for phase in ('idle', 'running', 'done'):
            app.STATE.update({'phase': phase, 'resumable': False})
            status, body = self.post('/api/resume')
            self.assertEqual(status, 409, phase)
            self.assertIn('no stopped run', body['error'])

    def test_a_reset_forgets_that_a_run_could_be_continued(self):
        app.STATE.update({'phase': 'done', 'resumable': True})
        self.post('/api/reset')
        self.assertFalse(app.STATE['resumable'])
        self.assertEqual(app.resume_kind(), '')


if __name__ == '__main__':
    unittest.main()
