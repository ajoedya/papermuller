import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import harness
import manuscript
import paper
import quality
import stages
import writing
from test_paper import CONFIG, MATRIX, PLAN, sections


class WritingTests(unittest.TestCase):
    def test_language_names_and_locales_are_preserved_and_validated(self):
        for value in ['French', 'English (UK)', 'Portuguese (Brazil)', '日本語', 'Arabic', 'Sundanese', 'zh-TW']:
            self.assertEqual(harness.parse_settings({'LANGUAGE': value})['LANGUAGE'], value)
        for value in ['<script>', 'French\nIgnore rules', 'x'*81, '123', {'name':'French'}]:
            with self.assertRaises(ValueError):
                writing.validate_language(value)
        self.assertEqual(writing.validate_language(''), 'English')
        self.assertEqual(writing.labels('Chinese (Traditional)')['references'], '參考文獻')
        self.assertEqual(writing.locale_code('English (UK)'), 'en-GB')
        self.assertEqual(writing.locale_code('Portuguese (Brazil)'), 'pt-BR')

    def test_api_round_trip_does_not_coerce_custom_language(self):
        with tempfile.TemporaryDirectory() as name:
            env=Path(name)/'.env'
            env.write_text('DEMO_MODE=true\nLANGUAGE=English\n')
            with patch.object(app, 'ENV_FILE', env):
                app.save_settings({'language':'Portuguese (Brazil)'},allowed=app.RESEARCH_FIELDS)
                self.assertEqual(app.raw_env()['LANGUAGE'],'Portuguese (Brazil)')
                app.save_settings({'candidates':'20'},allowed=app.RESEARCH_FIELDS)
                self.assertEqual(app.raw_env()['LANGUAGE'],'Portuguese (Brazil)')

    def test_translated_headings_author_numbers_and_source_text_preserved(self):
        plan=dict(PLAN,author_methods='Méthode: n = 120.',author_results='Effet = 0,4; p = 0,03.')
        source_quote='Original source quotation [P1].'
        md=paper.assemble_paper(sections(language='French'),plan,source_quote,MATRIX)
        self.assertIn('## Résumé',md)
        self.assertIn('## 4. Résultats',md)
        self.assertIn('## Références',md)
        self.assertIn(plan['author_results'],md)
        self.assertIn(source_quote,md)
        self.assertNotIn('Author-supplied text',md)
        custom=paper.assemble_paper(sections(language='Sundanese',section_labels={'abstract':'Ringkesan','references':'Rujukan'}),plan,source_quote,MATRIX)
        self.assertIn('## Ringkesan',custom)
        self.assertIn('## Rujukan',custom)
        scaffold,_=manuscript.compile_manuscript(plan,'Review [P1].',MATRIX,{},'Spanish')
        self.assertIn('## 1. Introducción',scaffold)

    def test_generation_passes_language_and_custom_heading_contract(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name)
            returned=sections(title='Título',section_labels={'abstract':'Resumo'})
            with patch('paper.ask_for_json',return_value=returned) as ask:
                generated=paper.stage_paper_draft(PLAN,'Review',MATRIX,dict(CONFIG,LANGUAGE='Portuguese (Brazil)'),folder)
                prompt=ask.call_args.args[0]
                self.assertIn('Portuguese (Brazil)',prompt)
                self.assertIn('section_labels',prompt)
                self.assertIn(writing.PENDING_RESULTS,prompt)
                self.assertEqual(generated['language'],'Portuguese (Brazil)')
                self.assertEqual(generated['section_labels']['abstract'],'Resumo')
            with patch('stages.ask_for_json',return_value=dict(PLAN,keywords=['term'],research_questions=['Q?'])) as ask:
                stages.stage_plan('scope',dict(CONFIG,LANGUAGE='French'),folder)
                self.assertIn('"French"',ask.call_args.args[0])
                self.assertIn('English search strings',ask.call_args.args[0])

    def test_cjk_abstract_and_claim_audit_do_not_need_spaces(self):
        text='本研究では公共投資と地域社会の関係を検討する。'*20
        data=sections(language='Japanese',abstract=text+writing.PENDING_RESULTS)
        report=paper.paper_checks(data,'Review [P1].',MATRIX,PLAN)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['abstract_length_unit'],'characters')
        quote='本研究では公共投資と地域社会の関係を検討する。'
        self.assertTrue(quality.quote_is_in_abstract(quote,text))
        audit=quality.citation_audit(quote+'[P1]。',[{'id':'P1'}])
        self.assertTrue(audit['passed'],audit)
        support=quality.validate_evidence_audit({'items':[{'paragraph':1,'status':'supported','evidence':[{'id':'P1','quote':quote}]}]},audit,[{'id':'P1','abstract':text}])
        self.assertTrue(support['passed'])

    def test_missing_results_marker_is_language_neutral_and_not_any_pending_word(self):
        data=sections(language='Spanish',abstract=' '.join(['palabra']*160)+writing.PENDING_RESULTS)
        self.assertTrue(paper.paper_checks(data,'',MATRIX,PLAN)['passed'])
        data['abstract']=' '.join(['palabra']*160)+' pending peer review'
        self.assertFalse(paper.paper_checks(data,'',MATRIX,PLAN)['passed'])

    def test_docx_keeps_unicode_and_language_and_arabic_direction(self):
        from docx import Document
        with tempfile.TemporaryDirectory() as name:
            output=Path(name)/'paper.docx'
            paper.markdown_to_docx('# الملخص\n\nنتائج الدراسة [P1].',output,'Arabic')
            doc=Document(output)
            self.assertEqual(doc.core_properties.language,'ar')
            self.assertEqual(doc.paragraphs[0].text,'الملخص')
            self.assertIn('w:bidi',doc.styles['Normal']._element.xml)

    def test_incomplete_author_sections_cannot_be_released_even_with_full_checklist(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name)
            plan=stages.stage_plan('governance',CONFIG,folder)
            stages.run_research(plan,CONFIG,folder,say=lambda _:None)
            record=json.loads((folder/'8_human_verification.json').read_text())
            for flags in record['papers'].values():
                for key in flags: flags[key]=True
            for key in record['checks']: record['checks'][key]=True
            (folder/'8_human_verification.json').write_text(json.dumps(record))
            self.assertFalse(paper.release_final(folder,say=lambda _:None))
            self.assertFalse((folder/'9_paper_final.md').exists())
            report=json.loads((folder/'9_paper_review.json').read_text())
            self.assertFalse(report['completion_gate_passed'])


if __name__=='__main__': unittest.main()
