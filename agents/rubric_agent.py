"""
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
