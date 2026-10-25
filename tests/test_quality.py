"""Run: python -m unittest discover -s tests -v (no internet required)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import quality
import stages


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.matrix = [{"id": "P1"}, {"id": "P2"}]
        self.papers = [
            {"id": "P1", "abstract": "Using fixed-effects panel data, road density reduces poverty through market access in rural districts."},
            {"id": "P2", "abstract": "Governance quality influences the performance of investment projects across several regions."},
        ]

    def test_doi_normalization(self):
        self.assertEqual(quality.normalize_doi('HTTPS://DOI.ORG/10.1234/ABC?x=y'), '10.1234/abc')
        self.assertEqual(quality.normalize_doi('doi: 10.1234/ABC'), '10.1234/abc')

    def test_exact_quotes_cannot_be_invented(self):
        excerpt = 'road density reduces poverty through market access in rural districts'
        self.assertTrue(quality.quote_is_in_abstract(excerpt, self.papers[0]['abstract']))
        self.assertFalse(quality.quote_is_in_abstract('road density conclusively proves growth across nations', self.papers[0]['abstract']))
        self.assertFalse(quality.quote_is_in_abstract('roads', self.papers[0]['abstract']))

    def test_empty_or_uncited_draft_fails(self):
        self.assertFalse(quality.citation_audit('', self.matrix)['passed'])
        draft = 'A substantive paragraph with no sources that attempts to explain what the cited literature finds.'
        audit = quality.citation_audit(draft, self.matrix)
        self.assertFalse(audit['passed'])
        self.assertEqual(audit['uncited_paragraphs'], [1])

    def test_fake_and_valid_ids(self):
        draft = 'A paragraph with sufficiently many words claims measurable differences in poverty levels [P1; P99].'
        audit = quality.citation_audit(draft, self.matrix)
        self.assertEqual(audit['unknown_ids'], ['P99'])
        self.assertFalse(audit['passed'])

    def test_uncited_second_paragraph_is_flagged(self):
        draft = ('Some long discussion about governance and poverty considers institutional capacity in the district [P1].\n\n'
                 'Additional claims follow here but have no cited studies to back the argument made in this paragraph.')
        audit = quality.citation_audit(draft, self.matrix)
        self.assertEqual(audit['uncited_paragraphs'], [2])

    def test_invalid_quotes_downgrade_model_support(self):
        draft = 'Roads relate to access and governance influences project implementation according to the surveyed evidence [P1; P2].'
        cite = quality.citation_audit(draft, self.matrix)
        raw = {'items': [{'paragraph': 1, 'status': 'supported', 'evidence': [
            {'id':'P1', 'quote': 'This quote was invented by the AI and is not in the abstract.'},
            {'id':'P2', 'quote': self.papers[1]['abstract']},
        ]}]}
        report = quality.validate_evidence_audit(raw, cite, self.papers)
        self.assertFalse(report['passed'])
        self.assertEqual(report['paragraphs'][0]['status'], 'partial')

    def test_omitted_paragraphs_fail(self):
        draft = ('An institutional question motivates the academic discussion in the literature reviewed for this proposal [P1].\n\n'
                 'Another academic paragraph discusses the impact of governance differences across project settings [P2].')
        cite = quality.citation_audit(draft, self.matrix)
        raw = {'items': [{'paragraph': 1, 'status': 'supported', 'evidence': [{'id': 'P1', 'quote': self.papers[0]['abstract']}]}]}
        report = quality.validate_evidence_audit(raw, cite, self.papers)
        self.assertFalse(report['passed'])
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['paragraphs'][1]['status'], 'unclear')

    def test_plan_validation(self):
        base = {'title': 'Public financial management', 'research_questions':['What is the relationship?'],
                'keywords': ['public financial management'], 'scope_note': 'Not specified'}
        self.assertEqual(stages.validate_plan(base, 'Original topic')['original_topic'], 'Original topic')
        with self.assertRaises(ValueError):
            stages.validate_plan({**base, 'keywords': []}, 'Original topic')

    def test_scope_gate_prevents_passing_high_score(self):
        config = {'DEMO_MODE': True, 'MAX_PAPERS': 12, 'MIN_VERIFIED': 5, 'REVISION_ROUNDS': 1,
                  'TARGET_SCORE': 8, 'LANGUAGE': 'English', 'CANDIDATES': 30}
        weak_scope = {k: 9 for k in stages.CRITERIA}
        weak_scope['scope_fidelity'] = 7
        review = {'scores': weak_scope, 'score': 8.7, 'fixes': [], 'strengths': []}
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            plan = stages.stage_plan('road infrastructure governance', config, folder)
            with patch('stages.stage_review', return_value=review.copy()):
                result = stages.run_research(plan, config, folder, say=lambda _x: None)
            self.assertEqual(result['verdict'], 'revise')
            self.assertEqual(result['status'], 'needs_scope_or_evidence_review')
            self.assertIn('DRAF SEMENTARA', (folder / '7_final_draft.md').read_text())

    def test_demo_full_workflow(self):
        config = {'DEMO_MODE': True, 'MAX_PAPERS': 12, 'MIN_VERIFIED': 5, 'REVISION_ROUNDS': 3,
                  'TARGET_SCORE': 8, 'LANGUAGE': 'English', 'CANDIDATES': 30}
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            plan = stages.stage_plan('road infrastructure governance', config, folder)
            result = stages.run_research(plan, config, folder, say=lambda _x: None)
            self.assertEqual(result['verdict'], 'accept')
            self.assertTrue(result['evidence_gate_passed'])
            self.assertTrue((folder / '7_final_evidence_audit.json').exists())
            audit1 = json.loads((folder / '6_citation_audit_v1.json').read_text())
            self.assertEqual(audit1['unknown_ids'], ['P99'])
            self.assertIn('DRAF UNTUK VERIFIKASI PENELITI', (folder / '7_final_draft.md').read_text())


if __name__ == '__main__':
    unittest.main()
