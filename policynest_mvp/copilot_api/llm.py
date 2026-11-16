"""Model provider layer for the applicant assistant. Standard library only.

Gemini (REST) is the default when GEMINI_API_KEY is set; Anthropic stays available when only its key is set.
Neither key is ever logged, returned or put in an error message: callers see exception class names only.

generate(kw) takes the request shape main.build_request makes (system, messages [{role, content}], max_tokens)
and returns (stop_reason, text) where stop_reason is "refusal" when the provider blocked the answer.
"""
import json
import os
import time
import urllib.error
import urllib.request

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "20"))


class LLMError(Exception):
    """Upstream failure. Carries only a short code, never a body or a key."""


def _valid(k):
    return bool(k) and not k.startswith("your-") and len(k) >= 20


def gemini_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    return k if _valid(k) else ""


def anthropic_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return k if (k and not k.startswith("your-")) else ""


def provider():
    """'gemini' (default when its key is set), 'anthropic', or None."""
    if gemini_key():
        return "gemini"
    if anthropic_key():
        return "anthropic"
    return None


def configured():
    return provider() is not None


def model():
    if provider() == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    return os.environ.get("COPILOT_MODEL", "claude-opus-5-5")


def fallback_model():
    return os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")


def _contents(messages):
    out = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        out.append({"role": role, "parts": [{"text": str(m.get("content", ""))}]})
    return out


def gemini_body(kw):
    return {
        "systemInstruction": {"parts": [{"text": kw["system"]}]},
        "contents": _contents(kw["messages"]),
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max(1024, min(int(kw.get("max_tokens", 2048)), 4096)),
                             "thinkingConfig": {"thinkingLevel": "low"}},
    }


def _post(model_name, body, opener=None):
    req = urllib.request.Request(GEMINI_URL.format(model=model_name), data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": gemini_key()})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_gemini(data):
    """(stop_reason, text) from a generateContent response. A blocked prompt or answer is a refusal."""
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return "refusal", ""
    cands = data.get("candidates") or []
    if not cands:
        return "refusal", ""
    c = cands[0]
    parts = (c.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    if c.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION") and not text:
        return "refusal", ""
    return "end_turn", text


RETRYABLE = (429, 500, 502, 503, 504)


def _without_thinking(body):
    b = json.loads(json.dumps(body))
    (b.get("generationConfig") or {}).pop("thinkingConfig", None)
    return b


def _try(model_name, body, post, fallback=False):
    """One model, one retry (after a short pause) on a transient failure. Raises LLMError('transient'|'fatal').
    A fallback model that rejects the request with a 400 is retried once without thinkingConfig."""
    last = "transient"
    stripped = False
    for attempt in range(3):
        try:
            return parse_gemini(post(model_name, body))
        except urllib.error.HTTPError as e:
            if fallback and e.code == 400 and not stripped:
                stripped = True
                body = _without_thinking(body)
                continue
            last = "transient" if e.code in RETRYABLE else "fatal"
            if last == "fatal":
                break
            if attempt >= 1:
                break
            time.sleep(0.7)
            continue
        except (TimeoutError, urllib.error.URLError, OSError, ValueError):
            last = "transient"
            if attempt >= 1:
                break
    raise LLMError(last)


def generate_gemini(kw, post=None):
    post = post or _post
    body = gemini_body(kw)
    try:
        return _try(model(), body, post)
    except LLMError:
        fb = fallback_model()
        if not fb or fb == model():
            raise
        return _try(fb, body, post, fallback=True)


def generate_anthropic(kw):
    import anthropic  # lazy: not needed when Gemini is configured
    kw = dict(kw)
    kw["model"] = os.environ.get("COPILOT_MODEL", "claude-opus-5-5")
    kw.setdefault("output_config", {"effort": os.environ.get("COPILOT_EFFORT", "low")})
    client = anthropic.Anthropic()
    if kw["model"].startswith("claude-haiku"):
        r = client.messages.create(**kw)
    else:
        try:
            r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        except (anthropic.BadRequestError, TypeError):
            r = client.messages.create(**kw)
    return r.stop_reason, "".join(b.text for b in r.content if b.type == "text").strip()


def generate(kw):
    p = provider()
    if p == "gemini":
        return generate_gemini(kw)
    if p == "anthropic":
        return generate_anthropic(kw)
    raise LLMError("no_key")
