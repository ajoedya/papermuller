"""
llm.py  -  THE "BRAIN" CONNECTION
==================================
This file has one job: send a question to an AI model and bring back the answer.

In REAL mode it talks to the configured AI gateway over the internet.
In DEMO mode it returns pre-written answers, so you can test for free.

You normally never need to edit this file.
"""

import json
import time

# Optional per-request observer for the local UI. No prompt/credentials are logged.
EVENT_HOOK = None

def _report(event):
    if EVENT_HOOK:
        try:
            EVENT_HOOK(event)
        except Exception:
            pass  # Observability must never break a research run.

# Which settings key chooses the model for each AI call. The first non-empty
# key wins; MODEL is the final fallback.
ROLE_MODELS = {
    "brainstorm": ("PLAN_MODEL",),
    "plan": ("PLAN_MODEL",), "screen": ("SCREEN_MODEL",),
    "matrix": ("EVIDENCE_MODEL",), "outline": ("OUTLINE_MODEL", "WRITER_MODEL"),
    "draft": ("WRITER_MODEL",), "evidence_audit": ("VERIFIER_MODEL",),
    "review": ("REVIEW_MODEL",), "redteam": ("REDTEAM_MODEL", "REVIEW_MODEL"),
    "paper_draft": ("PAPER_MODEL", "WRITER_MODEL"),
    "paper_review": ("PAPER_REVIEW_MODEL", "REVIEW_MODEL"),
}


def model_for_stage(stage, settings):
    """The configured model string (possibly comma-separated fallbacks) for a stage."""
    for key in ROLE_MODELS.get(stage, ()):
        if str(settings.get(key) or "").strip():
            return str(settings[key]).strip()
    return str(settings.get("MODEL") or "openrouter/free").strip()
import urllib.request
import urllib.error
from urllib.parse import urlparse

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
def _base(settings):
    return str(settings.get("LLM_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
def _is_openrouter(settings):
    return _base(settings) == DEFAULT_BASE_URL


def provider_name(settings):
    host = urlparse(_base(settings)).hostname
    return {"openrouter.ai": "OpenRouter", "api.wflabs.ai.id": "WFLabs"}.get(host, "AI provider")


def _key(settings):
    return str(settings.get("LLM_API_KEY") or (settings.get("OPENROUTER_API_KEY") if _is_openrouter(settings) else "") or "").strip()


def _http_hint(code, settings):
    name = provider_name(settings)
    return {
        401: f"{name} rejected the API key (HTTP 401). Check the key and API base URL in Settings; confirm the key is active.",
        402: f"{name} balance is empty or negative (HTTP 402). Check your credits.",
        403: f"{name} denied access (HTTP 403). The key may be inactive or this model is not allowed.",
        404: f"{name} did not find the model or endpoint (HTTP 404). Check the base URL and choose an ID from its model list.",
        429: f"{name} quota, balance, or rate limit exceeded (HTTP 429). Check your account and retry later.",
    }.get(code, f"{name} request failed (HTTP {code}). Check the service status and model availability.")


def ask(prompt, settings, stage="general", system="You are a careful academic research assistant."):
    """
    Send `prompt` to the AI and return its reply as plain text.

    prompt   : the instruction/question we send
    settings : the dictionary loaded from your .env file
    stage    : a label (used only by demo mode to pick a fake answer)
    """
    if settings["DEMO_MODE"]:
        from demo_data import fake_llm_answer
        answer = fake_llm_answer(stage, prompt)
        _report({"stage": stage, "model": "Demo simulator (offline)", "simulated": True, "usage": {}})
        return answer

    # ---- Build the message in the format OpenRouter expects ----
    # MODEL can be one name, or several separated by commas.
    # With several, OpenRouter automatically tries the next one if the first fails.
    configured = model_for_stage(stage, settings)
    models = [m.strip() for m in configured.split(",") if m.strip()]
    body = {
        "model": models[0],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,  # low = more careful, less "creative"
    }
    if len(models) > 1 and _is_openrouter(settings):
        body["models"] = models  # OpenRouter-only fallback mechanism
    skip = [p.strip() for p in settings.get("IGNORE_PROVIDERS", "").split(",") if p.strip()]
    if skip and _is_openrouter(settings):
        body["provider"] = {"ignore": skip}

    # Generic gateways do not understand OpenRouter's models array.
    candidates = models[:1] if _is_openrouter(settings) else models
    for index, model in enumerate(candidates):
        body["model"] = model
        for attempt in (1, 2, 3):
            try:
                return _send(body, settings, stage)
            except _ModelUnavailable as problem:
                if index == len(candidates) - 1:
                    raise SystemExit(f"\n[AI ERROR] {problem}\n") from None
                break
            except _Retry as problem:
                if attempt == 3:
                    if index == len(candidates) - 1:
                        raise SystemExit(f"\n[AI ERROR] {problem}\n") from None
                    break
                print(f"   ! {problem} Waiting 20 seconds, then retrying ({attempt}/2)...")
                time.sleep(20)


class _Retry(Exception):
    """A temporary problem worth trying again (busy or unavailable model)."""


class _ModelUnavailable(Exception):
    """An unrecognized model; an explicitly configured fallback may work."""


REQUESTS_USED = [0]  # counts real requests, so you can watch your daily free quota


def _send(body, settings, stage="general"):
    key = _key(settings)
    if not key:
        raise SystemExit("\n[AI SETTINGS] Enter the AI provider API key in Settings.\n")
    REQUESTS_USED[0] += 1
    request = urllib.request.Request(
        _base(settings) + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
    )

    # ---- Send it, and give a friendly message if something goes wrong ----
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # Gateways may reflect credentials in their body; do not echo it.
        if error.code == 404:
            raise _ModelUnavailable(_http_hint(error.code, settings)) from None
        if error.code in (429, 500, 502, 503, 504):
            raise _Retry(_http_hint(error.code, settings)) from None
        raise SystemExit(f"\n[AI ERROR {error.code}] {_http_hint(error.code, settings)}\n") from None

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        raise _Retry('Model connection failed or returned invalid JSON.') from None

    if not isinstance(data, dict):
        raise _Retry('Provider returned an invalid response object.')
    choices = data.get('choices')
    message = choices[0].get('message') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise _Retry('Provider returned no usable text. Try another model or inspect provider availability.')
    _report({"stage": stage, "model": str(data.get("model") or body["model"]),
             "simulated": False, "usage": data.get("usage") if isinstance(data.get("usage"), dict) else {}})
    return content


MODELS_URL = DEFAULT_BASE_URL + "/models"


def list_models(free_only=True, settings=None):
    """Load a gateway catalogue. OpenRouter is public; WFLabs requires a key."""
    settings = settings or {}
    headers = {"User-Agent": "papermuller/1.0"}
    if not _is_openrouter(settings):
        key = _key(settings)
        if not key:
            raise RuntimeError(f"Enter the {provider_name(settings)} API key before loading its model list.")
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(_base(settings) + "/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Could not load the {provider_name(settings)} model list. {_http_hint(error.code, settings)}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError(f"Could not load the {provider_name(settings)} model list: connection failed or invalid JSON.") from None
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise RuntimeError(f"{provider_name(settings)} returned an invalid model catalogue.")
    models = []
    for item in data.get("data", []):
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "")
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        free = (_is_openrouter(settings) and model_id.endswith(":free")) or (str(pricing.get("prompt")) in ("0", "0.0")
                                              and str(pricing.get("completion")) in ("0", "0.0"))
        if model_id and (free or not free_only or not _is_openrouter(settings)):
            models.append({"id": model_id, "name": str(item.get("name") or model_id)[:120],
                           "free": free, "context": item.get("context_length")})
    models.sort(key=lambda m: (not m["free"], m["id"]))
    routers = [{"id": "openrouter/free", "name": "OpenRouter Free router", "free": True, "context": None}] if _is_openrouter(settings) else []
    if not free_only and _is_openrouter(settings):
        routers.append({"id": "openrouter/auto", "name": "OpenRouter Auto (may be paid)", "free": False, "context": None})
    return routers + [m for m in models if m["id"] not in ("openrouter/free", "openrouter/auto")]


def ask_for_json(prompt, settings, stage="general"):
    """
    Same as ask(), but we expect the AI to answer in JSON (structured data).
    AI models sometimes wrap JSON in extra words or break it, so we cut out the
    {...} part, and if it is still broken we ask the model again (max 3 tries).
    """
    reply = ""
    for attempt in (1, 2, 3):
        reply = ask(prompt + "\n\nAnswer ONLY with valid JSON, no extra text.", settings, stage)
        start, end = reply.find("{"), reply.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(reply[start:end + 1])
            except json.JSONDecodeError:
                pass
        print(f"   ! The AI returned broken JSON. Asking again ({attempt}/3)...")
    raise SystemExit(f"\n[AI ERROR] Expected JSON but got:\n{reply[:500]}\n")
