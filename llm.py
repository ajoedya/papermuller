"""
llm.py  -  THE "BRAIN" CONNECTION
==================================
This file has one job: send a question to an AI model and bring back the answer.

In REAL mode it talks to OpenRouter over the internet.
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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
    if len(models) > 1:
        body["models"] = models  # the backup list
    skip = [p.strip() for p in settings.get("IGNORE_PROVIDERS", "").split(",") if p.strip()]
    if skip:
        body["provider"] = {"ignore": skip}  # never send requests to these servers

    for attempt in (1, 2, 3):  # try up to 3 times if the model is busy or down
        try:
            return _send(body, settings, stage)
        except _Retry as problem:
            if attempt == 3:
                raise SystemExit(f"\n[AI ERROR] {problem}\n")
            print(f"   ! {problem} Waiting 20 seconds, then retrying ({attempt}/2)...")
            time.sleep(20)


class _Retry(Exception):
    """A temporary problem worth trying again (busy or unavailable model)."""


REQUESTS_USED = [0]  # counts real requests, so you can watch your daily free quota


def _send(body, settings, stage="general"):
    REQUESTS_USED[0] += 1
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + settings["OPENROUTER_API_KEY"],
            "Content-Type": "application/json",
        },
    )

    # ---- Send it, and give a friendly message if something goes wrong ----
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        if error.code in (404, 429, 500, 502, 503):
            try:  # pull out OpenRouter's own explanation so you can see the real cause
                err = json.loads(detail)["error"]
                reason = err["message"]
                meta = err.get("metadata") or {}
                if meta.get("provider_name"):  # which server actually failed, and why
                    reason += f" | provider: {meta['provider_name']} | {str(meta.get('raw', ''))[:120]}"
            except (ValueError, KeyError, TypeError):
                reason = detail[:150]
            raise _Retry(f"Model busy or unavailable (error {error.code}): {reason}")
        hints = {
            401: "Your API key is wrong or missing. Check OPENROUTER_API_KEY in .env",
            402: "Your OpenRouter balance is empty or negative. Add credits.",
        }
        raise SystemExit(f"\n[AI ERROR {error.code}] {hints.get(error.code, detail)}\n")

    if "choices" not in data:  # some providers return an error inside a normal reply
        raise _Retry(f"Provider error: {str(data.get('error', data))[:150]}.")
    _report({"stage": stage, "model": str(data.get("model") or body["model"]),
             "simulated": False, "usage": data.get("usage") or {}})
    return data["choices"][0]["message"]["content"]


MODELS_URL = "https://openrouter.ai/api/v1/models"


def list_models(free_only=True):
    """Fetch OpenRouter's public model catalogue (no API key is sent)."""
    request = urllib.request.Request(MODELS_URL, headers={"User-Agent": "papermuller/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load the OpenRouter model list: {error}")
    models = []
    for item in data.get("data", []):
        model_id = str(item.get("id") or "")
        pricing = item.get("pricing") or {}
        free = model_id.endswith(":free") or (str(pricing.get("prompt")) in ("0", "0.0")
                                              and str(pricing.get("completion")) in ("0", "0.0"))
        if model_id and (free or not free_only):
            models.append({"id": model_id, "name": str(item.get("name") or model_id)[:120],
                           "free": free, "context": item.get("context_length")})
    models.sort(key=lambda m: (not m["free"], m["id"]))
    routers = [{"id": "openrouter/free", "name": "OpenRouter Free router", "free": True, "context": None}]
    if not free_only:
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
