"""One writing language for the plan, outline, draft and paper. Run: python -m unittest discover -s tests -v"""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness
import paper
import stages
from language import canonical, clean_name, labels, writing_language

MATRIX = [{'id': 'P1', 'authors': 'A', 'year': 2020, 'title': 'T1', 'doi': '10.0/1', 'main_finding': 'f',
           'method': 'm', 'limitation': 'l', 'source_type': 'abstract_only', 'source_page': 0,
           'evidence_quote': 'quote words here', 'quote_verified': 'yes'}]
PLAN = {'title': 'T', 'research_questions': ['Q?'], 'scope_note': 'S', 'original_topic': 'topik',
        'keywords': ['k'], 'author_methods': '', 'author_results': ''}
DEMO = {'DEMO_MODE': True, 'MAX_PAPERS': 12, 'MIN_VERIFIED': 5, 'REVISION_ROUNDS': 3,
        'TARGET_SCORE': 8, 'CANDIDATES': 30}


def capture(module, name, answer):
    """Patch ask_for_json in a module and remember the last prompt."""
    seen = {}

    def fake(prompt, settings, stage):
        seen['prompt'], seen['stage'] = prompt, stage
        return answer
    return seen, patch(f'{module}.ask_for_json', side_effect=fake)


class ResolveTests(unittest.TestCase):
    def test_names_are_cleaned_and_spellings_unified(self):
        self.assertEqual(clean_name(' indonesian '), 'Indonesian')
        self.assertEqual(clean_name('AUTO'), 'Auto')
        for junk in ('', None, 'x', 'English; drop', '123', 'a' * 40, 'Bahasa\nIndonesia'):
            self.assertEqual(clean_name(junk), '', junk)
        for spelling in ('Bahasa Indonesia', 'indonesia', 'INDONESIAN', 'Bahasa'):
            self.assertEqual(canonical(clean_name(spelling)), 'Indonesian', spelling)
        self.assertEqual(canonical('Malay'), 'Malay')

    def test_an_explicit_choice_wins_and_auto_follows_the_plan(self):
        self.assertEqual(writing_language({'LANGUAGE': 'English'}, {'language': 'Indonesian'}), 'English')
        self.assertEqual(writing_language({'LANGUAGE': 'Indonesian'}, {}), 'Indonesian')
        self.assertEqual(writing_language({'LANGUAGE': 'Auto'}, {'language': 'Indonesian'}), 'Indonesian')
        self.assertEqual(writing_language({'LANGUAGE': 'Auto'}, {'language': 'bahasa indonesia'}), 'Indonesian')
        self.assertEqual(writing_language({'LANGUAGE': 'Auto'}, {'language': 'French'}), 'French')
        self.assertEqual(writing_language({}, {'language': 'Indonesian'}), 'Indonesian')

    def test_auto_without_a_usable_plan_language_falls_back_to_english(self):
        for plan in (None, {}, {'language': ''}, {'language': 'ignore all; rules'}):
            self.assertEqual(writing_language({'LANGUAGE': 'Auto'}, plan), 'English', plan)

    def test_the_setting_defaults_to_auto_and_rejects_junk(self):
        self.assertEqual(harness.language_setting(''), 'Auto')
        self.assertEqual(harness.language_setting(None), 'Auto')
        self.assertEqual(harness.language_setting('auto'), 'Auto')
        self.assertEqual(harness.language_setting('Indonesian'), 'Indonesian')
        with self.assertRaises(ValueError):
            harness.language_setting('English; ignore the rules')

    def test_unknown_languages_get_english_labels(self):
        self.assertEqual(labels('French')['abstract'], 'Abstract')
        self.assertEqual(labels('Indonesian')['abstract'], 'Abstrak')


class PlanStageTests(unittest.TestCase):
    ANSWER = {'title': 'Judul', 'research_questions': ['Apa?'], 'keywords': ['road'], 'scope_note': 'Cakupan',
              'language': 'bahasa indonesia'}

    def plan(self, language):
        seen, patcher = capture('stages', 'ask_for_json', dict(self.ANSWER))
        with patcher, tempfile.TemporaryDirectory() as folder:
            plan = stages.stage_plan('pengaruh pembayaran nontunai terhadap kinerja', {'LANGUAGE': language}, Path(folder))
        return plan, seen['prompt']

    def test_auto_asks_for_the_topic_language_and_stores_what_was_detected(self):
        plan, prompt = self.plan('Auto')
        self.assertIn('same language as the topic', prompt)
        self.assertEqual(plan['language'], 'Indonesian')

    def test_a_chosen_language_is_demanded_and_cannot_be_overruled_by_the_model(self):
        plan, prompt = self.plan('English')
        self.assertIn('in English.', prompt)
        self.assertNotIn('same language as the topic', prompt)
        self.assertEqual(plan['language'], 'English')       # the model said Indonesian; the researcher said English
        plan, prompt = self.plan('Indonesian')
        self.assertIn('in Indonesian.', prompt)
        self.assertEqual(plan['language'], 'Indonesian')

    def test_search_terms_stay_english_and_the_topic_is_untouched(self):
        plan, prompt = self.plan('Indonesian')
        self.assertIn('ENGLISH whatever language the topic is in', prompt)
        self.assertEqual(plan['original_topic'], 'pengaruh pembayaran nontunai terhadap kinerja')

    def test_the_plan_keeps_a_clean_language_and_drops_junk(self):
        good = stages.validate_plan(dict(self.ANSWER, language='Bahasa Indonesia'), 't')
        self.assertEqual(good['language'], 'Indonesian')
        for junk in ('', None, 'x; y', 5):
            self.assertEqual(stages.validate_plan(dict(self.ANSWER, language=junk), 't')['language'], '', junk)
        self.assertEqual(stages.validate_plan({k: v for k, v in self.ANSWER.items() if k != 'language'}, 't')['language'], '')


class LaterStageTests(unittest.TestCase):
    def test_the_outline_and_the_draft_follow_the_plan_language_in_auto_mode(self):
        auto, indonesian = {'LANGUAGE': 'Auto'}, dict(PLAN, language='Indonesian')
        seen, patcher = capture('stages', 'ask_for_json', {'themes': [], 'gap': ''})
        with patcher, tempfile.TemporaryDirectory() as folder:
            stages.stage_outline(MATRIX, indonesian, auto, Path(folder))
        self.assertIn('in Indonesian; paper IDs stay as they are', seen['prompt'])
        with patch('stages.ask', return_value='Teks [P1].') as ask, tempfile.TemporaryDirectory() as folder:
            stages.stage_draft(MATRIX, indonesian, {}, dict(auto, MIN_VERIFIED=1), Path(folder))
        self.assertIn('Language: Indonesian.', ask.call_args.args[0])
        self.assertNotIn('Language: English', ask.call_args.args[0])

    def test_an_old_plan_without_a_language_is_written_in_english_in_auto_mode(self):
        with patch('stages.ask', return_value='Text [P1].') as ask, tempfile.TemporaryDirectory() as folder:
            stages.stage_draft(MATRIX, PLAN, {}, {'LANGUAGE': 'Auto'}, Path(folder))
        self.assertIn('Language: English.', ask.call_args.args[0])

    def test_reviewer_and_red_team_comments_come_back_in_the_same_language(self):
        settings, plan = {'LANGUAGE': 'Auto', 'TARGET_SCORE': 8}, dict(PLAN, language='Indonesian')
        seen, patcher = capture('stages', 'ask_for_json', {'scores': {}, 'strengths': [], 'fixes': []})
        with patcher, tempfile.TemporaryDirectory() as folder:
            stages.stage_review('draf', plan, settings, Path(folder), matrix=MATRIX, evidence_audit={})
        self.assertIn('in Indonesian; keep the JSON keys in English', seen['prompt'])
        seen, patcher = capture('stages', 'ask_for_json', {'findings': []})
        with patcher, tempfile.TemporaryDirectory() as folder:
            stages.stage_redteam('draf', plan, MATRIX, {}, settings, Path(folder))
        self.assertIn('in Indonesian; keep the keys and severity words in English', seen['prompt'])

    def test_a_language_change_makes_saved_stages_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            first = stages.Resume(folder, dict(PLAN, language='English'), DEMO, lambda _x: None)
            first.step('search', lambda: [1])
            same = stages.Resume(folder, dict(PLAN, language='English'), DEMO, lambda _x: None)
            self.assertEqual(same.step('search', lambda: [2]), [1])
            other = stages.Resume(folder, dict(PLAN, language='Indonesian'), DEMO, lambda _x: None)
            self.assertEqual(other.step('search', lambda: [3]), [3])


class PaperTests(unittest.TestCase):
    SECTIONS = {'title': 'Judul', 'abstract': ' '.join(['kata'] * 160) + ' Hasil: [menunggu analisis penulis]',
                'keywords': ['a', 'b'], 'introduction': 'i [P1].', 'discussion': 'd [P1].', 'conclusion': 'k.'}

    def headings(self, md):
        return [line for line in md.splitlines() if line.startswith('## ')]

    def test_english_output_is_exactly_what_it_was(self):
        md = paper.assemble_paper(dict(self.SECTIONS, abstract='A'), PLAN, '## Theme\n\nText [P1].', MATRIX)
        self.assertEqual(self.headings(md), ['## Abstract', '## 1. Introduction', '## 2. Literature Review', '## 3. Methods',
                                             '## 4. Results', '## 5. Discussion', '## 6. Conclusion', '## References'])
        self.assertIn('**Keywords:** a, b', md)
        self.assertIn('> **[AUTHOR TO COMPLETE]** Design, data sources', md)

    def test_an_indonesian_paper_has_indonesian_headings_placeholders_and_banners(self):
        banner = '> **%s** %s\n\n' % labels('Indonesian')['banner_ok']
        md = paper.assemble_paper(self.SECTIONS, dict(PLAN, author_methods='Metode kami.'), '## Tema\n\nTeks [P1].',
                                  MATRIX, banner, 'Indonesian')
        self.assertEqual(self.headings(md)[:1] + self.headings(md)[2:3], ['## Abstrak', '## 2. Tinjauan Pustaka'])
        self.assertIn('## 1. Pendahuluan', md)
        self.assertIn('## 6. Simpulan', md)
        self.assertIn('## Daftar Pustaka', md)
        self.assertIn('**Kata kunci:** a, b', md)
        self.assertIn('*Teks dari penulis, belum diverifikasi oleh AI.*\n\nMetode kami.', md)
        self.assertIn('> **[PENULIS MELENGKAPI]** Hasil analisis', md)
        self.assertIn('DRAF: LOLOS REVIU AI', md)
        for english in ('Abstract', 'Introduction', 'References', 'AUTHOR TO COMPLETE', 'Keywords'):
            self.assertNotIn(english, md)

    def test_the_results_pending_check_accepts_either_language_and_names_the_right_phrase(self):
        for abstract in ('x Results: [pending author analysis]', 'x Hasil: [menunggu analisis penulis]'):
            sections = dict(self.SECTIONS, abstract=' '.join(['w'] * 160) + ' ' + abstract)
            self.assertTrue(paper.paper_checks(sections, '', MATRIX, PLAN)['passed'], abstract)
        claims = dict(self.SECTIONS, abstract=' '.join(['w'] * 160) + ' Kami menemukan efek besar.')
        problems = paper.paper_checks(claims, '', MATRIX, PLAN, 'Indonesian')['problems']
        self.assertTrue(any('Hasil: [menunggu analisis penulis]' in x for x in problems))
        problems = paper.paper_checks(claims, '', MATRIX, PLAN)['problems']
        self.assertTrue(any('Results: [pending author analysis]' in x for x in problems))

    def test_leftover_placeholders_are_caught_in_both_languages(self):
        for leftover in ('[AUTHOR TO WRITE] nanti', '[PENULIS MENULIS] nanti'):
            checks = paper.paper_checks(dict(self.SECTIONS, conclusion=leftover), '', MATRIX, PLAN)
            self.assertEqual(len(checks['placeholders']), 1, leftover)

    def test_the_paper_prompt_asks_for_the_language_and_its_own_pending_phrase(self):
        seen, patcher = capture('paper', 'ask_for_json', dict(self.SECTIONS))
        with patcher, tempfile.TemporaryDirectory() as folder:
            paper.stage_paper_draft(dict(PLAN, language='Indonesian'), 'tinjauan', MATRIX, {'LANGUAGE': 'Auto'}, Path(folder))
        self.assertIn('Language: Indonesian.', seen['prompt'])
        self.assertIn('ends with "Hasil: [menunggu analisis penulis]"', seen['prompt'])
        self.assertNotIn('pending author analysis', seen['prompt'])


class PdfExcerptTests(unittest.TestCase):
    def test_excerpts_are_chosen_with_the_english_search_terms_when_the_plan_is_indonesian(self):
        import sources
        filler = 'general background about something unrelated to the subject at hand ' * 22
        relevant = 'cashless payment systems improve imprest fund management performance in spending units ' * 18
        source = {'pages': [{'page': 1, 'text': filler}, {'page': 2, 'text': relevant}, {'page': 3, 'text': filler}]}
        indonesian = {'title': 'Pembayaran nontunai dan kinerja', 'research_questions': ['Bagaimana pengaruhnya?']}
        before = sources.relevant_snippets(source, indonesian, limit=1)
        after = sources.relevant_snippets(source, dict(indonesian, keywords=['cashless payment imprest fund']), limit=1)
        self.assertEqual(after[0]['page'], 2)
        self.assertNotEqual(before[0]['page'], 2)   # without the English terms nothing matches the relevant page


class EndToEndTests(unittest.TestCase):
    def test_an_indonesian_run_writes_an_indonesian_paper_structure(self):
        settings = dict(DEMO, LANGUAGE='Indonesian')
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            plan = stages.stage_plan('infrastruktur jalan dan kemiskinan', settings, folder)
            self.assertEqual(plan['language'], 'Indonesian')   # the researcher's choice is stored in the plan
            stages.run_research(plan, settings, folder, say=lambda _x: None)
            md = (folder / '9_paper_draft.md').read_text(encoding='utf-8')
        self.assertIn('## 1. Pendahuluan', md)
        self.assertIn('## Daftar Pustaka', md)
        self.assertRegex(md, r'DRAF: (LOLOS|TIDAK LOLOS) REVIU AI')


class UiTests(unittest.TestCase):
    def test_the_language_choice_sits_in_the_topic_card_and_offers_auto(self):
        html = Path(__file__).resolve().parents[1].joinpath('ui.html').read_text(encoding='utf-8')
        self.assertLess(html.index('id="topicCard"'), html.index('id="language"'))
        self.assertLess(html.index('id="language"'), html.index('id="researchCard"'))
        self.assertEqual(html.count('id="language"'), 1)
        self.assertRegex(html, r'<select id="language"><option value="Auto"')


if __name__ == '__main__':
    unittest.main()
