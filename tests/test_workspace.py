import copy
import json
import tempfile
import threading
import time
import unittest
import io
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app
import demo_data
import harness
import ideation
import llm
import stages
import usage


IDEAS = json.loads(demo_data.fake_llm_answer("brainstorm", ""))


class UsageTests(unittest.TestCase):
    def test_derived_totals_are_computed_per_response_without_double_counting(self):
        rows = {}
        usage.add_response(rows, "brainstorm", {"prompt_tokens": 10, "completion_tokens": 5})
        usage.add_response(rows, "1", {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0})
        usage.add_response(rows, "1", {"total_tokens": 8, "cost": .02})
        total = usage.totals(rows)
        self.assertEqual(total["total_tokens"], 28)
        self.assertEqual(total["prompt_tokens"], 13)
        self.assertEqual(total["completion_tokens"], 7)
        self.assertEqual(total["token_reports"], 3)
        self.assertEqual(total["prompt_reports"], 2)
        self.assertFalse(total["partial_tokens"])
        self.assertTrue(total["partial_cost"])
        self.assertAlmostEqual(total["cost"], .02)

    def test_missing_usage_is_distinct_from_reported_zero_and_demo_is_not_billed(self):
        rows = {}
        usage.add_response(rows, "brainstorm", {})
        self.assertFalse(usage.totals(rows)["has_tokens"])
        usage.add_response(rows, "1", {"total_tokens": 0, "cost": 0})
        usage.add_response(rows, "1", {"total_tokens": 9999, "cost": 100}, simulated=True)
        total = usage.totals(rows)
        self.assertTrue(total["has_tokens"])
        self.assertTrue(total["has_cost"])
        self.assertTrue(total["partial_tokens"])
        self.assertEqual(total["total_tokens"], 0)
        self.assertEqual(total["real_responses"], 2)
        self.assertEqual(total["simulated_calls"], 1)

    def test_invalid_usage_is_ignored(self):
        for value in (True, -1, float("nan"), float("inf"), "12", 1.5):
            self.assertEqual(usage.reported_values({"total_tokens": value}), {})
        self.assertEqual(usage.reported_values({"cost": float("nan")}), {})
        self.assertEqual(usage.reported_values({"prompt_tokens": 12}), {"prompt_tokens": 12})


class IdeationTests(unittest.TestCase):
    def test_bounded_history_language_and_exploratory_scope(self):
        history = [{"role": "user", "content": f"turn-{i}"} for i in range(20)]
        settings = {"LANGUAGE": "French", "DEMO_MODE": False, "MODEL": "base", "PLAN_MODEL": "planner"}
        with patch("ideation.llm.ask_for_json", return_value=IDEAS) as ask:
            result = ideation.brainstorm("Please compare feasible directions", history, settings)
            prompt = ask.call_args.args[0]
            self.assertNotIn('"turn-0"', prompt)
            self.assertIn('"turn-19"', prompt)
            self.assertIn("French", prompt)
            self.assertIn("not a literature search", prompt)
            self.assertEqual(ask.call_args.kwargs["stage"], "brainstorm")
            self.assertEqual(llm.model_for_stage("brainstorm", settings), "planner")
            self.assertEqual(result["ideas"][0]["questions"], IDEAS["ideas"][0]["questions"])

    def test_malformed_or_oversized_ideas_are_rejected(self):
        for bad in ([], {}, {"reply": "x", "ideas": []}, {"reply": "x", "ideas": [None]},
                    {"reply": "x", "ideas": [dict(IDEAS["ideas"][0], questions="wrong")]},
                    {"reply": "x", "ideas": [dict(IDEAS["ideas"][0], title="x" * 251)]}):
            with self.assertRaises(ValueError):
                ideation.validate_response(bad)
        for message in (None, "", "x" * 3001):
            with self.assertRaises(ValueError):
                ideation.brainstorm(message, [], {})

    def test_starting_questions_reach_planning_as_data(self):
        proposal = json.loads(demo_data.fake_llm_answer("plan", ""))
        questions = ["How can administrative capacity be compared?"]
        with tempfile.TemporaryDirectory() as name, patch("stages.ask_for_json", return_value=proposal) as ask:
            plan = stages.stage_plan("Governance", {"LANGUAGE": "English"}, Path(name), seed_questions=questions)
            self.assertIn(json.dumps(questions), ask.call_args.args[0])
            self.assertIn("not verified findings", ask.call_args.args[0])
            self.assertEqual(plan["problem_statement"], proposal["problem_statement"])
            legacy = dict(proposal)
            legacy.pop("problem_statement")
            self.assertEqual(stages.validate_plan(legacy)["problem_statement"], "")
            with self.assertRaises(ValueError):
                stages.validate_plan(dict(proposal, problem_statement="x" * 2001))


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.old_state = copy.deepcopy(app.STATE)
        self.old_requests = llm.REQUESTS_USED[0]
        self.old_port = app.PORT
        app.STATE.update(phase="idle", stage=0, folder="", topic="", plan=None, error="", log=[], events=[],
                         usage_by_stage={}, completed_steps=[], seed_questions=[],
                         brainstorm={"messages": [], "ideas": [], "error": "", "requests": 0})
        llm.REQUESTS_USED[0] = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = harness.parse_settings({"LANGUAGE": "English"})
        self.patches = [patch.object(app, "read_settings", return_value=(self.settings, "")),
                        patch.object(app, "PROJECTS", self.root)]
        for item in self.patches:
            item.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        app.PORT = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.wait_idle()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        for item in reversed(self.patches):
            item.stop()
        app.STATE.clear()
        app.STATE.update(self.old_state)
        llm.REQUESTS_USED[0] = self.old_requests
        app.PORT = self.old_port
        self.tmp.cleanup()

    def request(self, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        request = Request(f"http://127.0.0.1:{app.PORT}" + path, data=body,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def wait_idle(self):
        end = time.monotonic() + 5
        while app.JOB_LOCK.locked() and time.monotonic() < end:
            time.sleep(.01)
        self.assertFalse(app.JOB_LOCK.locked(), "The worker must release model-job admission")

    def test_brainstorm_blocks_overlapping_jobs_and_preserves_usage_into_plan(self):
        entered, release = threading.Event(), threading.Event()

        def reply(*args, **kwargs):
            entered.set()
            release.wait(3)
            llm.REQUESTS_USED[0] += 1
            llm._report({"stage": "brainstorm", "model": "provider/brainstorm", "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
            return IDEAS

        with patch("ideation.llm.ask_for_json", side_effect=reply):
            self.request("/api/brainstorm", {"message": "Help me compare directions"})
            self.assertTrue(entered.wait(2))
            try:
                for path, data in (("/api/brainstorm", {"message": "again"}), ("/api/plan", {"topic": "x"}),
                                   ("/api/check", {}), ("/api/reset", {}), ("/api/settings", {})):
                    with self.assertRaises(HTTPError) as error:
                        self.request(path, data)
                    self.assertEqual(error.exception.code, 409)
            finally:
                release.set()
            self.wait_idle()
        self.assertEqual(list(self.root.iterdir()), [])
        state = self.request("/api/status")
        self.assertEqual(state["phase"], "idle")
        self.assertEqual(state["usage_totals"]["total_tokens"], 15)
        self.assertEqual(state["requests"], 1)
        self.assertEqual(len(state["brainstorm"]["messages"]), 2)
        # Preflight calls in the same session must not vanish at plan creation.
        app.on_llm_event({"stage": "check", "model": "provider/check", "usage": {"total_tokens": 7}})
        llm.REQUESTS_USED[0] += 1
        proposal = json.loads(demo_data.fake_llm_answer("plan", ""))
        with patch("stages.ask_for_json", return_value=proposal):
            self.request("/api/plan", {"topic": "A selected direction", "seed_questions": ["An editable starting question?"]})
            self.wait_idle()
        state = self.request("/api/status")
        self.assertEqual(state["phase"], "approve")
        self.assertEqual(state["usage_totals"]["total_tokens"], 22)
        self.assertEqual(state["requests"], 2)
        saved = json.loads((Path(state["folder"]) / "0_brainstorm.json").read_text())
        self.assertEqual(saved["seed_questions"], ["An editable starting question?"])
        self.assertEqual(saved["selected_topic"], "A selected direction")
        self.assertEqual(len(saved["messages"]), 2)
        self.assertEqual(self.request(f"/files/{Path(state['folder']).name}/0_brainstorm.json"), saved)
        with zipfile.ZipFile(io.BytesIO(app.editorial.research_bundle(Path(state["folder"])))) as bundle:
            self.assertIn("0_brainstorm.json", bundle.namelist())

    def test_brainstorm_errors_preserve_conversation_and_allow_retry(self):
        app.STATE["brainstorm"]["messages"] = [{"role": "user", "content": "An earlier interest"}]
        with patch("ideation.brainstorm", side_effect=SystemExit("Provider unavailable")):
            self.request("/api/brainstorm", {"message": "Refine this idea"})
            self.wait_idle()
        state = self.request("/api/status")
        self.assertEqual(state["phase"], "idle")
        self.assertEqual(state["brainstorm"]["error"], "Provider unavailable")
        self.assertEqual(state["brainstorm"]["messages"][0]["content"], "An earlier interest")
        with patch("ideation.brainstorm", return_value=IDEAS):
            self.request("/api/brainstorm", {"message": "Try again"})
            self.wait_idle()
        self.assertEqual(app.STATE["brainstorm"]["error"], "")

    def test_input_limits_and_reset_clear_the_session(self):
        for path, data in (("/api/brainstorm", {"message": "x" * 3001}),
                           ("/api/plan", {"topic": "x", "seed_questions": ["x"] * 6})):
            with self.assertRaises(HTTPError) as error:
                self.request(path, data)
            self.assertEqual(error.exception.code, 400)
        with patch.object(app, "save_settings", side_effect=ValueError("Invalid research settings")):
            with self.assertRaises(HTTPError) as error:
                self.request("/api/plan", {"topic": "x", "research": {}})
            self.assertEqual(error.exception.code, 400)
        self.assertFalse(app.JOB_LOCK.locked())
        self.assertEqual(app.STATE["phase"], "idle")
        app.on_llm_event({"stage": "check", "model": "provider/check", "usage": {"total_tokens": 10}})
        self.assertEqual(self.request("/api/status")["usage_totals"]["total_tokens"], 10)
        self.request("/api/reset", {})
        state = self.request("/api/status")
        self.assertEqual(state["usage_totals"]["total_tokens"], 0)
        self.assertEqual(state["brainstorm"]["messages"], [])

    def test_unselected_language_blocks_generation_before_model_calls(self):
        self.settings["LANGUAGE"] = ""
        with patch("ideation.brainstorm") as brainstorm, patch("stages.stage_plan") as plan:
            for path, payload in (("/api/brainstorm", {"message": "Help me explore"}),
                                  ("/api/brainstorm", {"message": "Help me explore", "language": ""}),
                                  ("/api/plan", {"topic": "Governance"}),
                                  ("/api/plan", {"topic": "Governance", "research": {"language": ""}})):
                with self.assertRaises(HTTPError) as error:
                    self.request(path, payload)
                self.assertEqual(error.exception.code, 400)
                self.assertIn("Choose a paper language", json.load(error.exception)["error"])
            brainstorm.assert_not_called()
            plan.assert_not_called()
        self.assertFalse(app.JOB_LOCK.locked())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_selected_language_overrides_previous_language_for_brainstorming(self):
        with patch("ideation.brainstorm", return_value=IDEAS) as brainstorm:
            self.request("/api/brainstorm", {"message": "Explore governance", "language": "Indonesian"})
            self.wait_idle()
            self.assertEqual(brainstorm.call_args.args[2]["LANGUAGE"], "Indonesian")
        self.assertEqual(self.settings["LANGUAGE"], "English")


if __name__ == "__main__":
    unittest.main()
