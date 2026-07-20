"""Convert outputs/batch_results.json -> eval/system_scores_50.csv (id,c1..c5).
Abstained/None criterion scores become 'A'.
Run from TrueScreen folder:  python eval\\results_to_csv.py
"""
import csv
import json
import os
import re

SRC = os.path.join("outputs", "batch_results.json")
DST = os.path.join("eval", "system_scores_50.csv")

data = json.load(open(SRC, encoding="utf-8"))
results = data.get("results", data) if isinstance(data, dict) else data

rows = []
for r in results:
    src = r.get("source") or r.get("filename") or r.get("file") or ""
    m = re.search(r"(resume_\d+)", str(src))
    if not m:
        print(f"skip (no resume id in source): {src}")
        continue
    rid = m.group(1)
    row = {"id": rid}
    pcs = r.get("per_criterion") or r.get("criteria") or []
    for pc in pcs:
        cid = pc.get("criterion_id") or pc.get("id") or ""
        score = pc.get("score", None)
        status = str(pc.get("status", "")).lower()
        if score is None or "abstain" in status:
            row[cid] = "A"
        else:
            # scores may be float; metrics expects 1-5 ints -> round
            row[cid] = int(round(float(score)))
    rows.append(row)

rows.sort(key=lambda x: x["id"])
crits = ["c1", "c2", "c3", "c4", "c5"]
with open(DST, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id"] + crits)
    for row in rows:
        w.writerow([row["id"]] + [row.get(c, "") for c in crits])

print(f"Wrote {DST}: {len(rows)} rows")
missing = [row["id"] for row in rows if any(row.get(c, "") == "" for c in crits)]
if missing:
    print(f"WARNING - rows with missing criterion scores: {missing}")
    print("If many are missing, the JSON keys differ from expected -"
          " paste the first entry of batch_results.json to Claude.")
