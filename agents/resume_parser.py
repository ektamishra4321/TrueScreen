"""
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
    text = "\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
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
