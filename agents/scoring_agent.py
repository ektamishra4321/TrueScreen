"""
scoring_agent.py — score one parsed resume against a rubric.

THE GUARDRAIL:
  * Every criterion score must cite 1-3 verbatim quotes from the resume.
  * verify_evidence_detail() checks each quote deterministically:
      "exact"  — literal substring (whitespace/case-normalized)
      "gapped" — quote words appear in order within a tight window
                 (handles two-column PDF extraction interleaving)
      None     — fabricated -> score nullified
  * No evidence -> abstain (score null), never guess.
  * Weighted totals computed in Python — the LLM does no arithmetic.
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
    return re.sub(r"\s+", " ", s).strip().lower()


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _gapped_match(quote: str, raw_text: str, slack: int = 6) -> bool:
    """True if quote's words appear in order in raw_text within a tight window.

    Handles two-column PDF interleaving: a few foreign tokens may be spliced
    into the middle of a real phrase. Window = len(quote tokens) + slack.
    Fabricated quotes fail: their words don't appear in order anywhere.
    """
    q = _tokens(quote)
    t = _tokens(raw_text)
    if len(q) < 3:
        return False
    max_span = len(q) + slack
    # try every occurrence of the first token as an anchor
    for start in (i for i, w in enumerate(t) if w == q[0]):
        qi = 1
        for j in range(start + 1, min(start + max_span, len(t))):
            if t[j] == q[qi]:
                qi += 1
                if qi == len(q):
                    return True
    return False


def verify_evidence_detail(quote: str, raw_text: str) -> str | None:
    """Returns "exact", "gapped", or None (fabricated)."""
    q = _normalize(quote)
    if len(q) < 8:
        return None
    if q in _normalize(raw_text):
        return "exact"
    if _gapped_match(quote, raw_text):
        return "gapped"
    return None


def verify_evidence(quote: str, raw_text: str) -> bool:
    """Back-compat bool wrapper (exact OR gapped counts as verified)."""
    return verify_evidence_detail(quote, raw_text) is not None


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
            verdicts = [verify_evidence_detail(q, raw_text) for q in evidence]
            if any(v is None for v in verdicts):
                fabricated = [q for q, v in zip(evidence, verdicts) if v is None]
                score, status = 0, "evidence_fabricated"
                evidence = fabricated  # keep them for the audit trail
            elif any(v == "gapped" for v in verdicts):
                status = "ok_gapped_extraction"
        audited.append({
            "criterion_id": cid, "criterion": crit["name"],
            "weight": crit["weight"], "score": score, "status": status,
            "evidence": evidence, "reasoning": s.get("reasoning", ""),
        })

    scored = [a for a in audited if a["score"] is not None]
    wsum = sum(a["weight"] for a in scored)
    total = round(sum(a["score"] * a["weight"] for a in scored) / wsum, 2) if wsum else None
    abstained = [a["criterion_id"] for a in audited if a["status"] == "no_evidence_abstained"]
    fabricated = [a["criterion_id"] for a in audited if a["status"] == "evidence_fabricated"]
    gapped = [a["criterion_id"] for a in audited if a["status"] == "ok_gapped_extraction"]
    return {
        "source": parsed_resume["source"],
        "candidate": (parsed_resume.get("structured") or {}).get("name"),
        "total_score_0_5": total,
        "abstained_criteria": abstained,
        "fabricated_evidence_criteria": fabricated,
        "gapped_extraction_criteria": gapped,
        "per_criterion": audited,
    }
