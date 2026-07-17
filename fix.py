"""
fix.py — TrueScreen patch 1: dynamic Gemini model selection.

Problem: all hardcoded Gemini model names 404 (Google renamed models again).
Fix: build the model chain at runtime from ListModels, preferring flash-lite >
flash > anything else usable. Also adds a diagnostic mode.

Usage:
    python fix.py          (applies the patch to llm.py)
    python llm.py          (after patching: lists your available models + test call)
"""
from pathlib import Path

NEW_BLOCK = '''
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
'''

DIAG = '''

if __name__ == "__main__":
    # Diagnostic: python llm.py
    print("Your usable Gemini models (ranked):")
    for m in _build_model_chain():
        print("  ", m)
    print("\\nTest call...")
    print(complete("Reply with exactly: OK", "You follow instructions exactly.",
                   max_tokens=10).strip())
'''


def main():
    p = Path("llm.py")
    src = p.read_text(encoding="utf-8")
    start = src.index("# ------------------------------------------------------------------ Gemini")
    end = src.index("# ------------------------------------------------------------------ Anthropic")
    patched = src[:start] + NEW_BLOCK.strip() + "\n\n\n" + src[end:]
    # remove the now-unused hardcoded chain
    patched = patched.replace(
        '''GEMINI_MODEL_CHAIN = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemma-3-27b-it",
]
''', "")
    if "__main__" not in patched:
        patched += DIAG
    p.write_text(patched, encoding="utf-8", newline="\n")
    print("llm.py patched: dynamic model chain from ListModels.")
    print("Now run:  python llm.py   (should list models and print OK)")


if __name__ == "__main__":
    main()