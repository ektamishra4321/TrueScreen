# TrueScreen — Evidence-Grounded Hiring Screener + Eval Harness

**TrueScreen scores honestly or not at all.** Resumes are scored against a
JD-derived rubric where **every score must cite verbatim evidence from the
resume — and a deterministic verifier checks each quote actually exists**.
Fabricated quote -> score nullified. No evidence -> the agent abstains.

> The layer that judges the candidate cites its sources, and the layer that
> checks the citations contains no ML.

## Live demo
Landing page + working screener: run `python web_app.py` -> http://localhost:5000

## Architecture

```
JD ──> Rubric Agent ──> rubric.json (weights renormalized to 100, deterministic)
Resume PDF ──> pdfplumber ──> raw text ──┐   (scanned PDFs rejected honestly)
                                         ├──> Scoring Agent (LLM)
rubric.json ─────────────────────────────┘         │
                                                   ▼
                              verify_evidence_detail()  <- deterministic, no ML
                              exact | gapped | fabricated
                                                   │
                     abstain / nullify / accept ───┘
                                                   ▼
                                 weighted total (computed in Python, not by LLM)
```

## Guardrails
- **Evidence contract**: 1-3 verbatim quotes per criterion, verified as exact
  (whitespace/case-normalized) substrings of the raw PDF text.
- **Gapped verification**: real quotes split by two-column PDF extraction are
  recognized (words in order within a tight window) and marked
  `ok_gapped_extraction` — found by auditing a false fabrication flag on real
  Kaggle data.
- **NO_ANSWER contract**: no evidence -> abstain (score null), never guess.
- **No LLM arithmetic**: weights and totals are computed in Python.
- **Honest rejection**: image/scanned PDFs are rejected, not hallucinated.
- **Self-healing LLM layer**: Gemini model chain built at runtime from
  ListModels (no hardcoded model names to rot), thinkingBudget auto-retry,
  fence-tolerant JSON parsing, JSONL telemetry.

## Measured baseline (real Kaggle resumes, human golden labels)
| metric | value |
|---|---|
| within-1 agreement | 62.5% |
| exact agreement | 25% |
| MAE | 1.125 |
| abstention rate | 20% |

**Finding:** the LLM judge compresses scores toward 3 — it detects the
*presence* of evidence but under-weighs its *strength* (a 15-year career and a
one-line mention both scored 3). Calibrated anchor examples are the v2 fix.

## Quickstart
```
pip install -r requirements.txt
copy .env.example .env        # add GEMINI_API_KEY (free: aistudio.google.com)
python -m pytest              # 23 deterministic tests, no API key needed
python cli.py rubric --jd sample_data/jd_it_support.md
python cli.py batch --rubric outputs/rubric.json --dir data/resumes
python web_app.py             # landing + web demo
```

No resume PDFs? Build them from the Kaggle CSV (snehaanbhawal/resume-dataset):
```
python make_resumes.py --csv Resume.csv --n 5
```

## Eval harness
Hand-score resumes in `eval/golden_labels.json`:
```json
[{"source": "data\\resumes\\x.pdf", "human_scores": {"c1": 4, "c2": 2}}]
```
```
python eval/eval_harness.py --results outputs/batch_results.json --golden eval/golden_labels.json
```
Reports exact/within-1 agreement, MAE, confusion matrix, abstention rate, and
the biggest human-vs-model disagreements.

## Stack
Python · Flask · pdfplumber · Google Gemini free tier (self-healing model
rotation) or Anthropic · pytest · zero paid infrastructure
