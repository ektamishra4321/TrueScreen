"""
llm.py — the ONLY file that talks to an LLM provider.

Dual-provider: Google Gemini (free tier, primary) or Anthropic (if key present).
Battle scars from SahaayakAI baked in:
  * Gemini model self-healing: if the configured model 404s, call ListModels
    and rotate to the first working fallback.
  * thinkingConfig disabled (thinkingBudget: 0) with auto-retry if the model
    rejects the field.
  * Minimum output token floor so JSON never gets truncated mid-brace.
  * parse_json_block(): tolerant JSON extraction (strips ``` fences, prose).
  * JSONL telemetry of every call in telemetry/calls.jsonl
"""
from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

_working_gemini_model: str | None = None

TELEMETRY_DIR = Path("telemetry")
MIN_OUTPUT_TOKENS = 1200
TIMEOUT_S = 120


class LLMError(RuntimeError):
    pass


def _log(record: dict) -> None:
    TELEMETRY_DIR.mkdir(exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(TELEMETRY_DIR / "calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_json_block(text: str):
    """Tolerantly extract the first JSON object/array from LLM output.

    Handles: ```json fences, leading prose, trailing commentary.
    Raises LLMError if nothing parseable is found.
    """
    if text is None:
        raise LLMError("Empty LLM response")
    text = text.strip()
    # strip markdown fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find first { ... } or [ ... ] via brace matching
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    raise LLMError(f"No parseable JSON in response: {text[:200]}")


# ------------------------------------------------------------------ Gemini
_EXCLUDE_TOKENS = ("embedding", "aqa", "tts", "image", "imagen", "veo",
                   "audio", "live", "vision", "exp", "learnlm")


def _gemini_list_models() -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    names = []
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            names.append(m["name"].removeprefix("models/"))
    return names


def _rank(name: str) -> tuple:
    n = name.lower()
    return (
        0 if "flash-lite" in n else 1 if "flash" in n else 2 if "gemini" in n else 3,
        0 if "latest" in n else 1,
        len(n),
    )


def _build_model_chain() -> list[str]:
    """Chain built live from ListModels — no hardcoded names to rot."""
    available = _gemini_list_models()
    usable = [m for m in available
              if not any(tok in m.lower() for tok in _EXCLUDE_TOKENS)]
    usable.sort(key=_rank)
    if not usable:
        raise LLMError(
            "ListModels returned no usable generateContent models. "
            "Raw list: " + ", ".join(available[:20]))
    return usable[:6]


def _call_gemini(prompt: str, system: str, max_tokens: int) -> str:
    global _working_gemini_model
    chain = ([_working_gemini_model] if _working_gemini_model else []) or _build_model_chain()
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS),
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    last_err = "no models tried"
    for model in chain:
        tried_without_thinking = False
        for attempt in range(3):
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_KEY}")
            try:
                r = requests.post(url, json=body, timeout=TIMEOUT_S)
            except requests.exceptions.ReadTimeout:
                last_err = f"{model}: timeout"
                continue
            if r.status_code == 200:
                data = r.json()
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    last_err = f"{model}: unexpected shape {str(data)[:200]}"
                    break
                _working_gemini_model = model
                return text
            if (r.status_code == 400 and "thinking" in r.text.lower()
                    and not tried_without_thinking):
                body["generationConfig"].pop("thinkingConfig", None)
                tried_without_thinking = True
                continue
            if r.status_code == 429:
                time.sleep(20)
                last_err = f"{model}: 429 rate limited"
                continue
            last_err = f"{model}: HTTP {r.status_code} {r.text[:200]}"
            break  # 404 or other -> next model in chain
        # this model failed; if it was the cached one, rebuild the full chain
        if _working_gemini_model == model:
            _working_gemini_model = None
            chain = _build_model_chain()
    raise LLMError(f"All Gemini models failed. Last error: {last_err}")


# ------------------------------------------------------------------ Anthropic
def _call_anthropic(prompt: str, system: str, max_tokens: int) -> str:
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": max(max_tokens, MIN_OUTPUT_TOKENS),
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=TIMEOUT_S,
    )
    if r.status_code != 200:
        raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["content"][0]["text"]


# ------------------------------------------------------------------ public API
def complete(prompt: str, system: str = "You are a helpful assistant.",
             max_tokens: int = 2000) -> str:
    """Single entry point. Returns raw text."""
    t0 = time.time()
    provider = "gemini" if GEMINI_KEY else "anthropic" if ANTHROPIC_KEY else None
    if provider is None:
        raise LLMError("No API key set. Copy .env.example to .env and add a key.")
    try:
        if provider == "gemini":
            out = _call_gemini(prompt, system, max_tokens)
        else:
            out = _call_anthropic(prompt, system, max_tokens)
        _log({"provider": provider, "model": _working_gemini_model or "claude",
              "latency_s": round(time.time() - t0, 2),
              "prompt_chars": len(prompt), "output_chars": len(out), "ok": True})
        return out
    except Exception as e:
        _log({"provider": provider, "ok": False, "error": str(e)[:300],
              "latency_s": round(time.time() - t0, 2)})
        raise


def complete_json(prompt: str, system: str, max_tokens: int = 2000):
    """complete() + tolerant JSON parsing, with one repair retry."""
    raw = complete(prompt, system, max_tokens)
    try:
        return parse_json_block(raw)
    except LLMError:
        repair = complete(
            "Your previous reply was not valid JSON. Reply with ONLY the corrected "
            "JSON, no prose, no markdown fences.\n\nPrevious reply:\n" + raw[:4000],
            system, max_tokens)
        return parse_json_block(repair)


if __name__ == "__main__":
    # Diagnostic: python llm.py
    print("Your usable Gemini models (ranked):")
    for m in _build_model_chain():
        print("  ", m)
    print("\nTest call...")
    print(complete("Reply with exactly: OK", "You follow instructions exactly.",
                   max_tokens=10).strip())
