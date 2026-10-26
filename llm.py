"""
llm.py  -  THE "BRAIN" CONNECTION
==================================
This file has one job: send a question to an AI model and bring back the answer.

In REAL mode it talks to OpenRouter over the internet.
In DEMO mode it returns pre-written answers, so you can test for free.

You normally never need to edit this file.
"""

import json
import re
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
    "brainstorm": ("PLAN_MODEL",),
}


def model_for_stage(stage, settings):
    """The configured model string (possibly comma-separated fallbacks) for a stage."""
    for key in ROLE_MODELS.get(stage, ()):
        if str(settings.get(key) or "").strip():
            return str(settings[key]).strip()
    return str(settings.get("MODEL") or "openrouter/free").strip()
import http.client
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
    skip = [p.strip() for p in settings.get("IGNORE_PROVIDERS", "").split(",") if p.strip()]
    refused = []  # models OpenRouter will not serve to this app
    while models:
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
        if skip:
            body["provider"] = {"ignore": skip}  # never send requests to these servers
        try:
            return _send_with_retries(body, settings, stage)
        except _ModelGated as gated:
            refused.append(gated.model)
            if gated.model not in models:
                break  # a router picked it, so there is nothing of ours to drop
            print(f"   ! {gated.model} is not available to this app. Trying the next model, if any.")
            models = [m for m in models if m != gated.model]
    raise SystemExit(
        f"\n[AI ERROR 403] {', '.join(refused)} is only available through approved agent apps, so Papermuller "
        "cannot use it.\nChoose another model in Settings (AI models), or set MODEL in .env, for example "
        "openrouter/free or a paid model. You can list backups separated by commas.\n")


def _send_with_retries(body, settings, stage):
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


class _ModelGated(Exception):
    """OpenRouter refuses this model for this app (some free models are limited to agent apps)."""

    def __init__(self, model):
        super().__init__(model)
        self.model = model


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
        try:
            detail = error.read().decode("utf-8", errors="ignore")
        except (OSError, http.client.HTTPException):
            detail = ""  # the connection dropped while reading the error text
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
        if error.code == 403 and "agentic harness" in detail.lower():
            named = re.search(r"([\w.\-/:@+]+) is only available on agentic harnesses", detail)
            raise _ModelGated(named.group(1) if named else str(body.get("model", "")))
        hints = {
            401: "Your API key is wrong or missing. Check OPENROUTER_API_KEY in .env",
            402: "Your OpenRouter balance is empty or negative. Add credits.",
        }
        raise SystemExit(f"\n[AI ERROR {error.code}] {hints.get(error.code, detail)}\n")
    except (OSError, http.client.HTTPException, ValueError) as error:
        # The connection was reset, timed out, or the reply was cut off mid-way. This is common on
        # long requests such as drafts, so try again instead of ending the whole run.
        raise _Retry(f"Connection problem ({type(error).__name__}): {str(error)[:120] or 'no details'}")

    if "choices" not in data:  # some providers return an error inside a normal reply
        raise _Retry(f"Provider error: {str(data.get('error', data))[:150]}.")
    _report({"stage": stage, "model": str(data.get("model") or body["model"]),
             "simulated": False, "usage": data.get("usage") or {}})
    content = ((data["choices"] or [{}])[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        # Free models sometimes return an empty reply (content is null); retry instead of crashing later.
        raise _Retry("The model returned an empty reply.")
    return content


MODELS_URL = "https://openrouter.ai/api/v1/models"


def _price_per_million(value):
    """USD per one million tokens, from OpenRouter's per-token price string.

    None when the price is missing or not a real price (routers report -1)."""
    try:
        price = float(value) * 1_000_000
    except (TypeError, ValueError):
        return None
    return round(price, 4) if price >= 0 else None


def list_models(free_only=True, kind=None):
    """Fetch OpenRouter's public model catalogue (no API key is sent).

    kind is "free", "paid" or "all". When it is omitted, free_only decides:
    True lists free models only, False lists everything."""
    kind = kind if kind in ("free", "paid", "all") else ("free" if free_only else "all")
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
        if not model_id or (kind == "free" and not free) or (kind == "paid" and free):
            continue
        models.append({"id": model_id, "name": str(item.get("name") or model_id)[:120],
                       "free": free, "context": item.get("context_length"),
                       "prompt_price": _price_per_million(pricing.get("prompt")),
                       "completion_price": _price_per_million(pricing.get("completion"))})
    # Free models first; paid models cheapest first, so the affordable ones are easy to find.
    models.sort(key=lambda m: (not m["free"], m["prompt_price"] is None, m["prompt_price"] or 0, m["id"]))
    routers = []
    if kind in ("free", "all"):
        routers.append({"id": "openrouter/free", "name": "OpenRouter Free router", "free": True, "context": None,
                        "prompt_price": 0, "completion_price": 0})
    if kind in ("paid", "all"):
        routers.append({"id": "openrouter/auto", "name": "OpenRouter Auto (may be paid)", "free": False, "context": None,
                        "prompt_price": None, "completion_price": None})
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
