"""fix_truescreen.py — run from the truescreen repo root.
1. Deletes the accidental nested duplicate eval/golden50_pdf/eval/
2. Adds CI + Python badges to README
3. Reframes the stale n=8 metrics honestly (pilot label + 50-set in-progress note)
4. Creates eval/golden_labels_50.csv labeling template (50 rows, you fill c1-c5)
After running: review changes in GitHub Desktop, commit, push.
Then move this script to scripts/dev/.
"""
import csv, shutil, sys
from pathlib import Path

root = Path(".")
if not (root / "eval" / "golden50").is_dir():
    sys.exit("ERROR: run this from the truescreen repo root (eval/golden50 not found).")

# 1. nested duplicate
dup = root / "eval" / "golden50_pdf" / "eval"
if dup.exists():
    shutil.rmtree(dup)
    print("[1/4] Deleted nested duplicate eval/golden50_pdf/eval/")
else:
    print("[1/4] Nested duplicate already gone — skipped.")

# 2 + 3. README
rd = root / "README.md"
text = rd.read_text(encoding="utf-8")

badges = ("![CI](https://github.com/ektamishra4321/truescreen/actions/workflows/ci.yml/badge.svg)\n"
          "![Python](https://img.shields.io/badge/python-3.10%2B-blue)\n")
title = "# TrueScreen — Evidence-Grounded Hiring Screener + Eval Harness\n"
if "actions/workflows/ci.yml/badge.svg" not in text:
    if title not in text:
        sys.exit("ERROR: README title line not found — README changed? Aborting before edit.")
    text = text.replace(title, title + badges, 1)
    print("[2/4] Added CI badge to README.")
else:
    print("[2/4] CI badge already present — skipped.")

old_metrics = """## Measured baseline (real Kaggle resumes, human golden labels)
| metric | value |
|---|---|
| within-1 agreement | 62.5% |
| exact agreement | 25% |
| MAE | 1.125 |
| abstention rate | 20% |

**Finding:** the LLM judge compresses scores toward 3 — it detects the
*presence* of evidence but under-weighs its *strength* (a 15-year career and a
one-line mention both scored 3). Calibrated anchor examples are the v2 fix."""

new_metrics = """## Measured baseline — pilot, n=8 (real Kaggle resumes, human golden labels)
| metric | value |
|---|---|
| within-1 agreement | 62.5% |
| exact agreement | 25% |
| MAE | 1.125 |
| abstention rate | 20% |

**n=8 is a pilot, not a claim.** These numbers exist to prove the harness runs
end-to-end on real resumes; they are too small to be statistically meaningful.

**Finding (pilot):** the LLM judge compresses scores toward 3 — it detects the
*presence* of evidence but under-weighs its *strength* (a 15-year career and a
one-line mention both scored 3). Calibrated anchor examples are the v2 fix.

**Eval in progress:** a 50-resume golden set (`eval/golden50/`) is committed
against a frozen rubric (`eval/frozen_rubric.json`, RUBRIC v1.1). Headline
metric will be mean quadratic-weighted Cohen's kappa across criteria plus
within-1 % (`eval/metrics_kappa.py`). Repo rule: numbers appear here only once
a single command reproduces them."""

if old_metrics in text:
    text = text.replace(old_metrics, new_metrics, 1)
    print("[3/4] Reframed metrics section (n=8 pilot + in-progress note).")
elif "n=8 is a pilot" in text:
    print("[3/4] Metrics already reframed — skipped.")
else:
    sys.exit("ERROR: metrics section not found verbatim — README changed? Nothing else was modified; re-check manually.")
rd.write_text(text, encoding="utf-8", newline="\n")

# 4. labeling template
tmpl = root / "eval" / "golden_labels_50.csv"
if not tmpl.exists():
    with open(tmpl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "c1", "c2", "c3", "c4", "c5"])
        for i in range(1, 51):
            w.writerow([f"resume_{i:02d}", "", "", "", "", ""])
    print("[4/4] Created eval/golden_labels_50.csv template — fill 1-5 (or A for abstain) per criterion.")
else:
    print("[4/4] eval/golden_labels_50.csv already exists — skipped.")

print("\nDone. Review in GitHub Desktop -> commit -> push.")
