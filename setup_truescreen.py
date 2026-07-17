"""
setup_truescreen.py — one-shot scaffold for TrueScreen (Evidence-Grounded Hiring Screener + Eval Harness)

Usage (Windows):
    1. Put this file inside your empty project folder (e.g. truescreen)
    2. python setup_truescreen.py
    3. Follow the printed next steps.

Re-running never overwrites existing files unless you pass --force.
"""
import os
import sys

FILES = {}

# ---------------------------------------------------------------- requirements
FILES["requirements.txt"] = """pdfplumber>=0.11
python-dotenv>=1.0
requests>=2.31
pytest>=8.0
"""

# ---------------------------------------------------------------- .env.example
FILES[".env.example"] = """# Paste ONE of these keys. Gemini free tier: aistudio.google.com
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
"""

# ---------------------------------------------------------------- .gitignore
FILES[".gitignore"] = """.env
__pycache__/
*.pyc
outputs/
telemetry/
data/resumes/*.pdf
.pytest_cache/
"""

# ---------------------------------------------------------------- llm.py
FILES["llm.py"] = '''"""
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

GEMINI_MODEL_CHAIN = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemma-3-27b-it",
]
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
        f.write(json.dumps(record, ensure_ascii=False) + "\\n")


def parse_json_block(text: str):
    """Tolerantly extract the first JSON object/array from LLM output.

    Handles: ```json fences, leading prose, trailing commentary.
    Raises LLMError if nothing parseable is found.
    """
    if text is None:
        raise LLMError("Empty LLM response")
    text = text.strip()
    # strip markdown fences
    fence = re.search(r"```(?:json)?\\s*(.*?)```", text, re.DOTALL)
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
            if ch == "\\\\":
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
def _gemini_list_models() -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    names = []
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            names.append(m["name"].removeprefix("models/"))
    return names


def _pick_gemini_model() -> str:
    global _working_gemini_model
    if _working_gemini_model:
        return _working_gemini_model
    try:
        available = set(_gemini_list_models())
    except Exception:
        available = set()
    for cand in GEMINI_MODEL_CHAIN:
        if not available or cand in available:
            _working_gemini_model = cand
            return cand
    # nothing from our chain — take the first flash-ish available model
    for name in available:
        if "flash" in name:
            _working_gemini_model = name
            return name
    raise LLMError("No usable Gemini model found via ListModels")


def _call_gemini(prompt: str, system: str, max_tokens: int) -> str:
    global _working_gemini_model
    model = _pick_gemini_model()
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS),
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    tried_without_thinking = False
    for attempt in range(len(GEMINI_MODEL_CHAIN) + 2):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_KEY}"
        )
        try:
            r = requests.post(url, json=body, timeout=TIMEOUT_S)
        except requests.exceptions.ReadTimeout:
            if attempt == 0:
                continue  # one automatic retry on timeout
            raise LLMError("Gemini timed out twice")
        if r.status_code == 200:
            data = r.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise LLMError(f"Unexpected Gemini shape: {str(data)[:300]}")
        if r.status_code == 400 and "thinking" in r.text.lower() and not tried_without_thinking:
            body["generationConfig"].pop("thinkingConfig", None)
            tried_without_thinking = True
            continue
        if r.status_code in (404, 429):
            # rotate down the chain
            try:
                idx = GEMINI_MODEL_CHAIN.index(model)
            except ValueError:
                idx = -1
            if idx + 1 < len(GEMINI_MODEL_CHAIN):
                model = GEMINI_MODEL_CHAIN[idx + 1]
                _working_gemini_model = model
                continue
        raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    raise LLMError("Exhausted Gemini model chain")


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
            "JSON, no prose, no markdown fences.\\n\\nPrevious reply:\\n" + raw[:4000],
            system, max_tokens)
        return parse_json_block(repair)
'''

# ---------------------------------------------------------------- agents/__init__.py
FILES["agents/__init__.py"] = ""

# ---------------------------------------------------------------- agents/rubric_agent.py
FILES["agents/rubric_agent.py"] = '''"""
rubric_agent.py — turn a job description into a weighted scoring rubric.

Output schema (JSON):
{
  "role": "IT Support Specialist",
  "criteria": [
    {"id": "c1", "name": "...", "description": "...", "weight": 30,
     "signals": ["...", "..."]},
    ...
  ]
}
Weights are auto-renormalized to sum to exactly 100 (deterministic, no LLM).
"""
from __future__ import annotations
import json

from llm import complete_json

SYSTEM = (
    "You are a senior technical recruiter. You design objective, evidence-based "
    "scoring rubrics. You never invent requirements not present in the job "
    "description. Reply ONLY with JSON matching the requested schema."
)

PROMPT_TEMPLATE = """Read this job description and produce a scoring rubric.

Rules:
- 4 to 6 criteria, each grounded in the JD text.
- Each criterion: id (c1..cN), name, one-sentence description, integer weight,
  and 2-4 concrete "signals" (things in a resume that would count as evidence).
- Weights should roughly reflect importance and sum near 100 (I will renormalize).
- Do NOT include personality traits or anything unverifiable from a resume.

JOB DESCRIPTION:
---
{jd}
---

Reply ONLY with JSON:
{{"role": "...", "criteria": [{{"id": "c1", "name": "...", "description": "...",
  "weight": 30, "signals": ["..."]}}]}}"""


def renormalize_weights(criteria: list[dict]) -> list[dict]:
    """Deterministically scale integer weights to sum to exactly 100."""
    if not criteria:
        return criteria
    raw = [max(1, int(c.get("weight", 1))) for c in criteria]
    total = sum(raw)
    scaled = [round(w * 100 / total) for w in raw]
    # fix rounding drift on the largest item
    drift = 100 - sum(scaled)
    scaled[scaled.index(max(scaled))] += drift
    for c, w in zip(criteria, scaled):
        c["weight"] = w
    return criteria


def build_rubric(jd_text: str) -> dict:
    rubric = complete_json(PROMPT_TEMPLATE.format(jd=jd_text.strip()), SYSTEM)
    if "criteria" not in rubric or not isinstance(rubric["criteria"], list):
        raise ValueError("Rubric missing criteria list")
    rubric["criteria"] = renormalize_weights(rubric["criteria"])
    return rubric


def save_rubric(rubric: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rubric, f, indent=2, ensure_ascii=False)
'''

# ---------------------------------------------------------------- agents/resume_parser.py
FILES["agents/resume_parser.py"] = '''"""
resume_parser.py — PDF -> raw text -> structured resume JSON.

Two stages:
  1. pdfplumber text extraction (deterministic). If a PDF yields almost no
     text it is a scanned image — we REJECT it honestly instead of guessing.
  2. LLM structuring into {name, headline, skills, experience[], education[]}.

The raw text is preserved and travels with the parse — the scoring agent's
evidence verifier checks quotes against RAW TEXT, not the LLM structure.
"""
from __future__ import annotations
import re

import pdfplumber

from llm import complete_json

MIN_CHARS_FOR_REAL_TEXT = 300  # below this we assume a scanned/image PDF


class ScannedPDFError(ValueError):
    pass


def extract_text(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\\n".join(pages)
    text = re.sub(r"[ \\t]+", " ", text)
    if len(text.strip()) < MIN_CHARS_FOR_REAL_TEXT:
        raise ScannedPDFError(
            f"{pdf_path}: only {len(text.strip())} chars extracted — likely a "
            "scanned/image PDF. OCR is out of scope; rejecting honestly."
        )
    return text.strip()


SYSTEM = (
    "You extract structured data from resume text. You only use information "
    "actually present in the text. Unknown fields are null or empty lists. "
    "Reply ONLY with JSON."
)

PROMPT = """Structure this resume text.

RESUME TEXT:
---
{text}
---

Reply ONLY with JSON:
{{"name": "... or null", "headline": "... or null",
  "skills": ["..."],
  "experience": [{{"title": "...", "company": "...", "duration": "...",
                   "highlights": ["..."]}}],
  "education": [{{"degree": "...", "institution": "...", "year": "..."}}]}}"""


def parse_resume(pdf_path: str) -> dict:
    raw_text = extract_text(pdf_path)
    structured = complete_json(PROMPT.format(text=raw_text[:12000]), SYSTEM)
    return {"source": pdf_path, "raw_text": raw_text, "structured": structured}
'''

# ---------------------------------------------------------------- agents/scoring_agent.py
FILES["agents/scoring_agent.py"] = '''"""
scoring_agent.py — score one parsed resume against a rubric.

THE GUARDRAIL (this is the whole point of the project):
  * For every criterion the LLM must return 1-3 verbatim "evidence" quotes
    copied from the resume.
  * verify_evidence() deterministically checks each quote actually appears in
    the raw resume text (whitespace/case-normalized).
  * Any fabricated quote -> that criterion's score is NULLIFIED (set to 0,
    flagged "evidence_fabricated").
  * If the LLM finds no evidence it must ABSTAIN (score null, "no_evidence")
    rather than guess. The SahaayakAI NO_ANSWER contract, chapter two.

Scores are 0-5 per criterion. Weighted total is computed deterministically
in Python — the LLM never does arithmetic on the final score.
"""
from __future__ import annotations
import re

from llm import complete_json

SYSTEM = (
    "You are a rigorous hiring screener. You score ONLY from evidence literally "
    "present in the resume text. Every score MUST include verbatim quotes copied "
    "character-for-character from the resume. If you cannot find evidence for a "
    "criterion, you MUST abstain with score null and empty evidence. Fabricating "
    "or paraphrasing quotes is the worst possible failure. Reply ONLY with JSON."
)

PROMPT = """Score this resume against the rubric. 0-5 per criterion.

Scoring guide: 0 = no relevant evidence but you still judged (avoid — abstain
instead), 1 = weak tangential evidence, 3 = solid direct evidence, 5 = exceptional,
multiple strong signals.

RUBRIC:
{rubric}

RESUME TEXT:
---
{resume}
---

Reply ONLY with JSON:
{{"scores": [{{"criterion_id": "c1", "score": 3 or null,
   "evidence": ["verbatim quote from resume", "..."],
   "reasoning": "one sentence"}}]}}
Rules:
- evidence quotes must be EXACT substrings of the resume text (8-40 words each).
- score null + evidence [] means you abstain for that criterion.
"""


def _normalize(s: str) -> str:
    return re.sub(r"\\s+", " ", s).strip().lower()


def verify_evidence(quote: str, raw_text: str) -> bool:
    """Deterministic check: does the quote exist in the resume text?"""
    q = _normalize(quote)
    if len(q) < 8:
        return False
    return q in _normalize(raw_text)


def score_resume(parsed_resume: dict, rubric: dict) -> dict:
    import json as _json
    raw_text = parsed_resume["raw_text"]
    result = complete_json(
        PROMPT.format(rubric=_json.dumps(rubric, ensure_ascii=False),
                      resume=raw_text[:12000]),
        SYSTEM, max_tokens=3000)

    by_id = {c["id"]: c for c in rubric["criteria"]}
    audited = []
    for s in result.get("scores", []):
        cid = s.get("criterion_id")
        crit = by_id.get(cid)
        if crit is None:
            continue
        score = s.get("score", None)
        evidence = [e for e in s.get("evidence", []) if isinstance(e, str)]
        status = "ok"
        if score is None or not evidence:
            score, status, evidence = None, "no_evidence_abstained", []
        else:
            verified = [verify_evidence(q, raw_text) for q in evidence]
            if not all(verified):
                fabricated = [q for q, v in zip(evidence, verified) if not v]
                score, status = 0, "evidence_fabricated"
                evidence = fabricated  # keep the fabricated ones for the audit trail
        audited.append({
            "criterion_id": cid, "criterion": crit["name"],
            "weight": crit["weight"], "score": score, "status": status,
            "evidence": evidence, "reasoning": s.get("reasoning", ""),
        })

    # deterministic weighted total over non-abstained criteria
    scored = [a for a in audited if a["score"] is not None]
    wsum = sum(a["weight"] for a in scored)
    total = round(sum(a["score"] * a["weight"] for a in scored) / wsum, 2) if wsum else None
    abstained = [a["criterion_id"] for a in audited if a["status"] == "no_evidence_abstained"]
    fabricated = [a["criterion_id"] for a in audited if a["status"] == "evidence_fabricated"]
    return {
        "source": parsed_resume["source"],
        "candidate": (parsed_resume.get("structured") or {}).get("name"),
        "total_score_0_5": total,
        "abstained_criteria": abstained,
        "fabricated_evidence_criteria": fabricated,
        "per_criterion": audited,
    }
'''

# ---------------------------------------------------------------- eval/__init__.py
FILES["eval/__init__.py"] = ""

# ---------------------------------------------------------------- eval/eval_harness.py
FILES["eval/eval_harness.py"] = '''"""
eval_harness.py — compare model scores against human golden labels.

Golden file format (JSON):
[
  {"source": "data/resumes/foo.pdf",
   "human_scores": {"c1": 4, "c2": 2, ...}},
  ...
]

Metrics: exact agreement, within-1 agreement, MAE, per-criterion confusion
matrix (0-5), abstention rate, and the biggest disagreements for review.
Fully deterministic — no API key needed.
"""
from __future__ import annotations
import json
from collections import defaultdict


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate(model_results: list[dict], golden: list[dict]) -> dict:
    golden_by_source = {g["source"]: g["human_scores"] for g in golden}
    pairs = []          # (source, cid, human, model)
    abstentions = 0
    total_criteria = 0
    for r in model_results:
        human = golden_by_source.get(r["source"])
        if human is None:
            continue
        for pc in r["per_criterion"]:
            cid = pc["criterion_id"]
            if cid not in human:
                continue
            total_criteria += 1
            if pc["score"] is None:
                abstentions += 1
                continue
            pairs.append((r["source"], cid, int(human[cid]), int(pc["score"])))

    if not pairs:
        return {"error": "No overlapping scored criteria between results and golden."}

    exact = sum(1 for _, _, h, m in pairs if h == m)
    within1 = sum(1 for _, _, h, m in pairs if abs(h - m) <= 1)
    mae = sum(abs(h - m) for _, _, h, m in pairs) / len(pairs)

    confusion = defaultdict(int)
    for _, _, h, m in pairs:
        confusion[f"human_{h}->model_{m}"] += 1

    disagreements = sorted(pairs, key=lambda p: -abs(p[2] - p[3]))[:10]

    return {
        "n_compared": len(pairs),
        "exact_agreement": round(exact / len(pairs), 3),
        "within_1_agreement": round(within1 / len(pairs), 3),
        "mae": round(mae, 3),
        "abstention_rate": round(abstentions / total_criteria, 3) if total_criteria else 0,
        "confusion": dict(sorted(confusion.items())),
        "biggest_disagreements": [
            {"source": s, "criterion": c, "human": h, "model": m}
            for s, c, h, m in disagreements if h != m
        ],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="outputs/batch_results.json")
    ap.add_argument("--golden", required=True, help="eval/golden_labels.json")
    args = ap.parse_args()
    report = evaluate(load_json(args.results), load_json(args.golden))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
'''

# ---------------------------------------------------------------- cli.py
FILES["cli.py"] = '''"""
cli.py — TrueScreen command line.

Commands:
  python cli.py rubric --jd sample_data/jd_it_support.md
  python cli.py score  --rubric outputs/rubric.json --resume data/resumes/x.pdf
  python cli.py batch  --rubric outputs/rubric.json --dir data/resumes
  python eval/eval_harness.py --results outputs/batch_results.json --golden eval/golden_labels.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

OUT = Path("outputs")


def cmd_rubric(args):
    from agents.rubric_agent import build_rubric, save_rubric
    jd_text = Path(args.jd).read_text(encoding="utf-8")
    rubric = build_rubric(jd_text)
    OUT.mkdir(exist_ok=True)
    save_rubric(rubric, OUT / "rubric.json")
    print(f"Rubric for role: {rubric.get('role')}")
    for c in rubric["criteria"]:
        print(f"  {c['id']:>3}  w={c['weight']:>3}  {c['name']}")
    print(f"\\nSaved -> {OUT / 'rubric.json'}")


def cmd_score(args):
    from agents.resume_parser import parse_resume, ScannedPDFError
    from agents.scoring_agent import score_resume
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
    try:
        parsed = parse_resume(args.resume)
    except ScannedPDFError as e:
        print(f"REJECTED: {e}")
        sys.exit(1)
    result = score_resume(parsed, rubric)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_batch(args):
    from agents.resume_parser import parse_resume, ScannedPDFError
    from agents.scoring_agent import score_resume
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
    pdfs = sorted(Path(args.dir).glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {args.dir}")
        sys.exit(1)
    results, rejected = [], []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ... ", end="", flush=True)
        try:
            parsed = parse_resume(str(pdf))
            r = score_resume(parsed, rubric)
            results.append(r)
            flags = ""
            if r["abstained_criteria"]:
                flags += f" abstained:{len(r['abstained_criteria'])}"
            if r["fabricated_evidence_criteria"]:
                flags += f" FABRICATED:{len(r['fabricated_evidence_criteria'])}"
            print(f"score={r['total_score_0_5']}{flags}")
        except ScannedPDFError as e:
            rejected.append({"source": str(pdf), "reason": str(e)})
            print("REJECTED (scanned)")
        except Exception as e:
            rejected.append({"source": str(pdf), "reason": str(e)[:200]})
            print(f"ERROR: {str(e)[:120]}")
    OUT.mkdir(exist_ok=True)
    with open(OUT / "batch_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    with open(OUT / "batch_rejected.json", "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False)

    ranked = sorted([r for r in results if r["total_score_0_5"] is not None],
                    key=lambda r: -r["total_score_0_5"])
    print("\\n=== RANKING ===")
    for r in ranked:
        print(f"  {r['total_score_0_5']:>5}  {Path(r['source']).name}  "
              f"({r['candidate'] or 'name not found'})")
    print(f"\\nSaved -> {OUT / 'batch_results.json'} "
          f"({len(results)} scored, {len(rejected)} rejected)")


def main():
    ap = argparse.ArgumentParser(prog="truescreen")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("rubric", help="Build rubric from a JD")
    p.add_argument("--jd", required=True)
    p.set_defaults(fn=cmd_rubric)

    p = sub.add_parser("score", help="Score one resume PDF")
    p.add_argument("--rubric", required=True)
    p.add_argument("--resume", required=True)
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("batch", help="Score a folder of resume PDFs")
    p.add_argument("--rubric", required=True)
    p.add_argument("--dir", required=True)
    p.set_defaults(fn=cmd_batch)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
'''

# ---------------------------------------------------------------- sample JD
FILES["sample_data/jd_it_support.md"] = """# IT Support Specialist (L1/L2)

**Location:** Mumbai (hybrid) | **Experience:** 2-5 years

## About the role
We run IT operations for a 400-person fintech. You will own day-to-day support
tickets, endpoint management, and basic network troubleshooting.

## What you'll do
- Resolve L1/L2 tickets (Windows, macOS, O365/Google Workspace) within SLA
- Manage endpoints via Intune/Jamf; enforce security baselines
- Troubleshoot LAN/Wi-Fi/VPN issues; escalate network faults with evidence
- Maintain asset inventory and onboarding/offboarding checklists
- Write and update runbooks for recurring issues

## Must-have
- 2+ years hands-on IT support in a 100+ seat environment
- Strong Windows administration (AD, GPO, imaging)
- Ticketing discipline (Jira SM / Freshservice / ServiceNow)
- Clear written communication for runbooks and user comms

## Nice-to-have
- Scripting (PowerShell or Python) for automation
- Certifications: CompTIA A+/Network+, MS-102, ITIL Foundation
- Exposure to SOC2/ISO27001 controls
"""

# ---------------------------------------------------------------- tests
FILES["tests/__init__.py"] = ""

FILES["tests/test_parse_json_block.py"] = '''from llm import parse_json_block, LLMError
import pytest


def test_plain_json():
    assert parse_json_block('{"a": 1}') == {"a": 1}


def test_fenced_json():
    assert parse_json_block('```json\\n{"a": 1}\\n```') == {"a": 1}


def test_fence_without_lang():
    assert parse_json_block('```\\n{"a": 1}\\n```') == {"a": 1}


def test_prose_then_json():
    assert parse_json_block('Sure! Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_nested_braces_in_strings():
    assert parse_json_block('x {"a": "curly } inside", "b": 2} y') == {"a": "curly } inside", "b": 2}


def test_array_root():
    assert parse_json_block('here: [1, 2, 3] done') == [1, 2, 3]


def test_garbage_raises():
    with pytest.raises(LLMError):
        parse_json_block("no json here at all")
'''

FILES["tests/test_rubric_weights.py"] = '''from agents.rubric_agent import renormalize_weights


def test_weights_sum_to_100():
    crits = [{"weight": 30}, {"weight": 30}, {"weight": 30}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100


def test_uneven_weights_sum_to_100():
    crits = [{"weight": 7}, {"weight": 13}, {"weight": 1}, {"weight": 5}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100


def test_zero_and_missing_weights_survive():
    crits = [{"weight": 0}, {}, {"weight": 50}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100
    assert all(c["weight"] >= 1 for c in out[:2])
'''

FILES["tests/test_evidence_verifier.py"] = '''from agents.scoring_agent import verify_evidence

RESUME = """Ravi Kumar — IT Support Engineer
Managed Active Directory and GPO for a 250-seat office in Pune.
Resolved 40+ tickets weekly in Freshservice within SLA.
Automated onboarding with PowerShell scripts."""


def test_exact_quote_verifies():
    assert verify_evidence("Managed Active Directory and GPO for a 250-seat office", RESUME)


def test_whitespace_and_case_normalized():
    assert verify_evidence("managed   active directory AND gpo for a 250-seat office", RESUME)


def test_fabricated_quote_fails():
    assert not verify_evidence("Led a team of 15 engineers at Google", RESUME)


def test_paraphrase_fails():
    assert not verify_evidence("Handled AD and group policy for 250 seats", RESUME)


def test_too_short_quote_fails():
    assert not verify_evidence("SLA", RESUME)
'''

FILES["tests/test_eval_harness.py"] = '''from eval.eval_harness import evaluate


def _result(source, scores):
    return {
        "source": source,
        "per_criterion": [
            {"criterion_id": cid, "score": s} for cid, s in scores.items()
        ],
    }


def test_perfect_agreement():
    results = [_result("a.pdf", {"c1": 4, "c2": 2})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["exact_agreement"] == 1.0
    assert rep["mae"] == 0.0
    assert rep["biggest_disagreements"] == []


def test_within_one_and_mae():
    results = [_result("a.pdf", {"c1": 3, "c2": 5})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["exact_agreement"] == 0.0
    assert rep["within_1_agreement"] == 0.5
    assert rep["mae"] == 2.0


def test_abstention_counted():
    results = [_result("a.pdf", {"c1": None, "c2": 2})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["abstention_rate"] == 0.5
    assert rep["n_compared"] == 1
'''

# ---------------------------------------------------------------- README
FILES["README.md"] = """# TrueScreen — Evidence-Grounded Hiring Screener + Eval Harness

**TrueScreen scores honestly or not at all.** Resumes are scored against a
JD-derived rubric where **every score must cite verbatim
evidence from the resume — and a deterministic verifier checks each quote actually
exists**. Fabricated quote → score nullified. No evidence → the agent abstains.

> The layer that judges the candidate cites its sources, and the layer that
> checks the citations contains no ML.

## Architecture

```
JD ──> Rubric Agent ──> rubric.json (weights renormalized to 100, deterministic)
Resume PDF ──> pdfplumber ──> raw text ──┐   (scanned PDFs rejected honestly)
                                         ├──> Scoring Agent (LLM)
rubric.json ─────────────────────────────┘         │
                                                   ▼
                                    verify_evidence()  ← deterministic, no ML
                                                   │
                     abstain / nullify / accept ───┘
                                                   ▼
                                 weighted total (computed in Python, not by LLM)
```

## Guardrails
- **Evidence contract**: 1-3 verbatim quotes per criterion, checked as exact
  (whitespace/case-normalized) substrings of the raw PDF text.
- **NO_ANSWER contract**: no evidence → abstain (score null), never guess.
- **No LLM arithmetic**: weights and totals are computed in Python.
- **Honest rejection**: image/scanned PDFs are rejected, not hallucinated.

## Quickstart
```
pip install -r requirements.txt
copy .env.example .env        # add GEMINI_API_KEY (free: aistudio.google.com)
pytest                        # 12+ deterministic tests, no API key needed
python cli.py rubric --jd sample_data/jd_it_support.md
python cli.py batch --rubric outputs/rubric.json --dir data/resumes
```

## Eval harness
Label a handful of resumes yourself in `eval/golden_labels.json`:
```json
[{"source": "data/resumes/x.pdf", "human_scores": {"c1": 4, "c2": 2}}]
```
Then:
```
python eval/eval_harness.py --results outputs/batch_results.json --golden eval/golden_labels.json
```
Reports exact agreement, within-1 agreement, MAE, confusion matrix, abstention
rate, and the biggest human-vs-model disagreements for review.

## Stack
Python · pdfplumber · Google Gemini free tier (self-healing model rotation) or
Anthropic · pytest · zero paid infrastructure
"""

FILES["data/resumes/.gitkeep"] = ""
FILES["outputs/.gitkeep"] = ""


def main():
    force = "--force" in sys.argv
    created = skipped = 0
    for rel_path, content in FILES.items():
        path = os.path.join(os.getcwd(), rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.exists(path) and not force:
            skipped += 1
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        created += 1
    print(f"{created} files created, {skipped} skipped.")
    print("""
NEXT STEPS
  1. pip install -r requirements.txt
  2. copy .env.example .env   (then paste your GEMINI_API_KEY)
  3. pytest                   (all tests must pass — no API key needed)
  4. Copy 5 PDFs from the Kaggle INFORMATION-TECHNOLOGY folder into data\\resumes
  5. python cli.py rubric --jd sample_data/jd_it_support.md
  6. python cli.py batch --rubric outputs/rubric.json --dir data/resumes
""")


if __name__ == "__main__":
    main()
