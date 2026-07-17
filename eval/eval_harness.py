"""
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
