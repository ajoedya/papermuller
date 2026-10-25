import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import harness
import llm
import pipeline
import stages
import tools


class ResearchSettingsTests(unittest.TestCase):
    def test_year_range_and_filters_are_validated(self):
        s = harness.parse_settings({"FROM_YEAR": "2018", "TO_YEAR": "2024", "WORK_TYPE": "review"})
        self.assertEqual((s["FROM_YEAR"], s["TO_YEAR"], s["WORK_TYPE"]), (2018, 2024, "review"))
        self.assertEqual(harness.parse_settings({})["TO_YEAR"], harness.CURRENT_YEAR)
        self.assertEqual(harness.parse_settings({})["MODEL"], "openrouter/free")
        for bad in ({"FROM_YEAR": "2024", "TO_YEAR": "2018"}, {"FROM_YEAR": "abc"},
                    {"WORK_TYPE": "thesis"}, {"MIN_VERIFIED": "20", "MAX_PAPERS": "10"},
                    {"REVISION_ROUNDS": "11"}):
            with self.assertRaises(ValueError):
                harness.parse_settings(bad)

    def test_openalex_filter_string(self):
        text = tools.openalex_filter({"FROM_YEAR": 2018, "TO_YEAR": 2024, "WORK_TYPE": "article_review",
                                      "OPEN_ACCESS_ONLY": True, "MIN_CITATIONS": 5})
        self.assertEqual(text, "from_publication_date:2018-01-01,to_publication_date:2024-12-31,"
                               "type:article|review,is_oa:true,cited_by_count:>4")
        self.assertEqual(tools.openalex_filter({"FROM_YEAR": 2015}), "from_publication_date:2015-01-01")

    def test_search_drops_papers_outside_the_year_range(self):
        papers = [{"title": "a", "year": 2016, "doi": "10.1/a", "abstract": "x", "cited_by": 3},
                  {"title": "b", "year": 2021, "doi": "10.1/b", "abstract": "x", "cited_by": 3}]
        settings = {"DEMO_MODE": True, "FROM_YEAR": 2020, "TO_YEAR": 2024, "CANDIDATES": 10}
        with tempfile.TemporaryDirectory() as tmp, patch("stages.search_papers", return_value=papers):
            found = stages.stage_search({"keywords": ["k"]}, settings, Path(tmp))
            self.assertEqual([p["title"] for p in found], ["b"])
            saved = json.loads((Path(tmp) / "2_search_settings.json").read_text())
            self.assertEqual((saved["from_year"], saved["to_year"]), (2020, 2024))


class StageModelTests(unittest.TestCase):
    def test_fallback_chain(self):
        s = {"MODEL": "base", "WRITER_MODEL": "writer", "REVIEW_MODEL": "reviewer"}
        self.assertEqual(llm.model_for_stage("plan", s), "base")
        self.assertEqual(llm.model_for_stage("outline", s), "writer")
        self.assertEqual(llm.model_for_stage("redteam", s), "reviewer")
        s.update(PLAN_MODEL="planner", OUTLINE_MODEL="outliner", REDTEAM_MODEL="critic")
        self.assertEqual([llm.model_for_stage(k, s) for k in ("plan", "outline", "redteam")],
                         ["planner", "outliner", "critic"])

    def test_pipeline_exposes_editable_slots(self):
        steps = pipeline.describe({"MODEL": "base", "WRITER_MODEL": "writer"})
        slots = {slot["key"]: slot for step in steps for slot in step["model_slots"]}
        self.assertEqual(set(slots), {"PLAN_MODEL", "SCREEN_MODEL", "EVIDENCE_MODEL", "OUTLINE_MODEL",
                                      "WRITER_MODEL", "VERIFIER_MODEL", "REVIEW_MODEL", "REDTEAM_MODEL"})
        self.assertEqual(slots["OUTLINE_MODEL"]["effective"], "writer")
        self.assertEqual(slots["OUTLINE_MODEL"]["inherits"], "WRITER_MODEL")
        self.assertEqual(steps[1]["model_slots"], [])  # OpenAlex stage has no model

    def test_model_catalogue_parsing(self):
        payload = {"data": [
            {"id": "vendor/paid", "name": "Paid", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
            {"id": "vendor/small:free", "name": "Small", "pricing": {"prompt": "0", "completion": "0"}}]}
        body = io.BytesIO(json.dumps(payload).encode())
        body.__enter__ = lambda *a: body
        body.__exit__ = lambda *a: False
        with patch("urllib.request.urlopen", return_value=body):
            ids = [m["id"] for m in llm.list_models(True)]
        self.assertEqual(ids, ["openrouter/free", "vendor/small:free"])


class SettingsApiTests(unittest.TestCase):
    def test_partial_update_keeps_other_keys_and_rejects_bad_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("DEMO_MODE=true\nMODEL=openrouter/free\nFROM_YEAR=2015\nOPENROUTER_API_KEY=\n", encoding="utf-8")
            with patch.object(app, "ENV_FILE", env):
                app.save_settings({"writer_model": "vendor/model:free"})
                app.save_settings({"from_year": "2019", "to_year": "2023"}, allowed=app.RESEARCH_FIELDS)
                text = env.read_text()
                self.assertIn("WRITER_MODEL=vendor/model:free", text)
                self.assertIn("FROM_YEAR=2019", text)
                self.assertIn("MODEL=openrouter/free", text)
                with self.assertRaises(ValueError):
                    app.save_settings({"from_year": "2030", "to_year": "2020"})
                with self.assertRaises(ValueError):
                    app.save_settings({"plan_model": "bad model; rm -rf"})
                # Research-only updates cannot change keys or models.
                app.save_settings({"model": "vendor/other", "candidates": "20"}, allowed=app.RESEARCH_FIELDS)
                self.assertIn("MODEL=openrouter/free", env.read_text())
                self.assertIn("CANDIDATES=20", env.read_text())


if __name__ == "__main__":
    unittest.main()
