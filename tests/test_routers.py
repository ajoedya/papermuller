import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import app
import harness
import llm


WFLABS = "https://api.wflabs.ai.id/v1"
CATALOGUE = {"data": [{"id": "wf/deepseek-v4.1-flash"}, {"id": "wf/glm-5.3-flash"},
                      {"id": "wf/unknown-price:free"}]}


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


class RouterTests(unittest.TestCase):
    def test_unsaved_url_and_key_are_used_without_writing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            before = "DEMO_MODE=true\nOPENROUTER_API_KEY=sk-or-old\nMODEL=openrouter/free\n"
            env.write_text(before)
            with patch.object(app, "ENV_FILE", env), patch("urllib.request.urlopen", return_value=response(CATALOGUE)) as send:
                models = app.model_catalogue({"llm_base_url": WFLABS, "openrouter_key": "wf-new", "free_only": True})
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, WFLABS + "/models")
                self.assertEqual(request.get_header("Authorization"), "Bearer wf-new")
                self.assertEqual({m["id"] for m in models}, {p["id"] for p in CATALOGUE["data"]})
                self.assertTrue(all(not m["free"] for m in models))
                self.assertEqual(env.read_text(), before)

    def test_saved_wflabs_key_can_load_models_despite_unrelated_invalid_settings(self):
        raw = {"LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-saved", "MODEL": "openrouter/free", "FROM_YEAR": "invalid"}
        with patch.object(app, "raw_env", return_value=raw), patch("urllib.request.urlopen", return_value=response(CATALOGUE)) as send:
            app.model_catalogue({})
            self.assertEqual(send.call_args.args[0].get_header("Authorization"), "Bearer wf-saved")

    def test_changed_endpoint_never_receives_a_saved_key(self):
        raw = {"LLM_BASE_URL": llm.DEFAULT_BASE_URL, "LLM_API_KEY": "sk-or-private"}
        with patch.object(app, "raw_env", return_value=raw), patch("urllib.request.urlopen") as send:
            with self.assertRaisesRegex(RuntimeError, "Enter the WFLabs API key"):
                app.model_catalogue({"llm_base_url": WFLABS})
            send.assert_not_called()

    def test_legacy_key_is_only_used_for_openrouter(self):
        with patch("urllib.request.urlopen", return_value=response(CATALOGUE)) as send:
            llm.list_models(False, {"OPENROUTER_API_KEY": "sk-or-old"})
            self.assertIsNone(send.call_args.args[0].get_header("Authorization"))
        with self.assertRaises(harness.MissingAPIKeyError):
            harness.parse_settings({"DEMO_MODE": "false", "LLM_BASE_URL": WFLABS,
                                    "MODEL": "wf/glm-5.3-flash", "OPENROUTER_API_KEY": "sk-or-old"})

    def test_provider_mismatches_and_endpoint_paths_are_rejected(self):
        for raw in ({"LLM_BASE_URL": WFLABS, "LLM_API_KEY": "sk-or-private", "MODEL": "wf/model"},
                    {"LLM_API_KEY": "wf-private"}, {"MODEL": "wf/model"},
                    {"LLM_BASE_URL": WFLABS, "MODEL": "wf/model", "WRITER_MODEL": "openrouter/free"},
                    {"LLM_BASE_URL": WFLABS + "/models"}, {"LLM_BASE_URL": WFLABS + "/chat/completions"},
                    {"LLM_BASE_URL": "https://api.example.org/\n/v1"}):
            with self.subTest(raw={k: v for k, v in raw.items() if "KEY" not in k}), self.assertRaises(ValueError) as error:
                harness.parse_settings(raw)
            self.assertNotIn("private", str(error.exception))

    def test_wflabs_chat_uses_standard_fields_and_its_bearer_key(self):
        settings = {"DEMO_MODE": False, "LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-test",
                    "MODEL": "wf/model,wf/backup", "IGNORE_PROVIDERS": "ignored"}
        with patch("urllib.request.urlopen", return_value=response({"choices": [{"message": {"content": "OK"}}]})) as send:
            self.assertEqual(llm.ask("hello", settings), "OK")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, WFLABS + "/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer wf-test")
            body = json.loads(request.data)
            self.assertEqual(body["model"], "wf/model")
            self.assertNotIn("models", body)
            self.assertNotIn("provider", body)

    def test_openrouter_keeps_server_side_fallbacks(self):
        with patch.object(llm, "_send", return_value="OK") as send:
            llm.ask("hi", {"DEMO_MODE": False, "MODEL": "vendor/one,vendor/two", "IGNORE_PROVIDERS": "A"})
            body = send.call_args.args[0]
            self.assertEqual(body["models"], ["vendor/one", "vendor/two"])
            self.assertEqual(body["provider"], {"ignore": ["A"]})

    def test_wflabs_401_has_correct_provider_and_no_secret_or_retry(self):
        settings = {"DEMO_MODE": False, "LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-private", "MODEL": "wf/model"}
        for catalogue in (True, False):
            error = HTTPError(WFLABS + "/models", 401, "unauthorized", {}, io.BytesIO(b'wf-private'))
            with patch("urllib.request.urlopen", side_effect=error), patch("llm.time.sleep") as sleep:
                with self.assertRaises(RuntimeError if catalogue else SystemExit) as failed:
                    llm.list_models(settings=settings) if catalogue else llm.ask("hello", settings)
                message = str(failed.exception)
                self.assertIn("WFLabs", message)
                self.assertIn("401", message)
                self.assertNotIn("OpenRouter", message)
                self.assertNotIn("wf-private", message)
                sleep.assert_not_called()

    def test_wflabs_unknown_model_uses_explicit_fallback(self):
        settings = {"DEMO_MODE": False, "LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-test", "MODEL": "wf/missing,wf/backup"}
        error = HTTPError(WFLABS, 404, "missing", {}, None)
        with patch("urllib.request.urlopen", side_effect=[error, response({"choices": [{"message": {"content": "OK"}}]})]) as send, patch("llm.time.sleep") as sleep:
            self.assertEqual(llm.ask("hello", settings), "OK")
            self.assertEqual([json.loads(c.args[0].data)["model"] for c in send.call_args_list], ["wf/missing", "wf/backup"])
            sleep.assert_not_called()
        failures = [HTTPError(WFLABS, 503, "busy", {}, None) for _ in range(3)]
        with patch("urllib.request.urlopen", side_effect=failures + [response({"choices": [{"message": {"content": "OK"}}]})]) as send, patch("llm.time.sleep") as sleep:
            self.assertEqual(llm.ask("hello", settings), "OK")
            self.assertEqual([json.loads(c.args[0].data)["model"] for c in send.call_args_list],
                             ["wf/missing"] * 3 + ["wf/backup"])
            self.assertEqual(sleep.call_count, 2)

    def test_auth_failure_does_not_try_backup_models(self):
        settings = {"DEMO_MODE": False, "LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-test", "MODEL": "wf/one,wf/two"}
        with patch("urllib.request.urlopen", side_effect=HTTPError(WFLABS, 403, "denied", {}, None)) as send:
            with self.assertRaises(SystemExit):
                llm.ask("hello", settings)
            self.assertEqual(send.call_count, 1)

    def test_malformed_model_catalogues_have_controlled_errors(self):
        for payload in ([], {}, {"data": None}, {"data": {}}):
            with patch("urllib.request.urlopen", return_value=response(payload)):
                with self.assertRaisesRegex(RuntimeError, "invalid model catalogue"):
                    llm.list_models(settings={"LLM_BASE_URL": WFLABS, "LLM_API_KEY": "wf-test"})

    def test_switching_provider_requires_replacement_key_and_preserves_other_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("DEMO_MODE=true\nLLM_API_KEY=sk-or-old\nMODEL=openrouter/free\nEMAIL=keep@example.org\n")
            with patch.object(app, "ENV_FILE", env):
                with self.assertRaisesRegex(ValueError, "new AI provider API key"):
                    app.save_settings({"llm_base_url": WFLABS, "model": "wf/glm-5.3-flash"})
                app.save_settings({"llm_base_url": WFLABS, "openrouter_key": "wf-new", "model": "wf/glm-5.3-flash"})
                app.save_settings({"openrouter_key": ""})
                self.assertIn("LLM_API_KEY=wf-new", env.read_text())
                self.assertIn("EMAIL=keep@example.org", env.read_text())
                # Only flags, never credentials, are exposed to the browser.
                with patch.object(app, "read_settings", return_value=(None, "")):
                    self.assertNotIn("wf-new", json.dumps(app.public_settings()))


if __name__ == "__main__":
    unittest.main()
