"""TrueScreen eval metrics: quadratic-weighted Cohen's kappa + within-1 agreement.
Usage:
  python eval/metrics_kappa.py --golden eval/golden_labels_50.csv --system eval/system_scores_50.csv

Both CSVs need columns: id, c1, c2, c3, c4, c5
- golden: your hand labels (1-5, or 'A' for human-abstain)
- system: TrueScreen's scores (1-5, or 'A' where the system ABSTAINED)
Requires: pip install scikit-learn
"""
import argparse
import csv
import sys

try:
    from sklearn.metrics import cohen_kappa_score
except ImportError:
    sys.exit("Missing sklearn. Run: pip install scikit-learn --break-system-packages"
             if sys.platform != "win32" else "Missing sklearn. Run: pip install scikit-learn")

CRITERIA = ["c1", "c2", "c3", "c4", "c5"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--system", required=True)
    args = ap.parse_args()

    g, s = load(args.golden), load(args.system)
    ids = sorted(set(g) & set(s))
    if not ids:
        sys.exit("No overlapping ids between the two files.")
    print(f"Matched resumes: {len(ids)}")

    kappas = []
    sys_abstains = 0
    total_cells = 0
    print(f"\n{'crit':<6}{'n':>4}{'kappa_qw':>10}{'within-1%':>11}{'excluded':>10}")
    for c in CRITERIA:
        gv, sv, excluded = [], [], 0
        for i in ids:
            gval, sval = g[i].get(c, "").strip(), s[i].get(c, "").strip()
            total_cells += 1
            if sval.upper() == "A":
                sys_abstains += 1
            if not gval or not sval or gval.upper() == "A" or sval.upper() == "A":
                excluded += 1
                continue
            try:
                gv.append(int(gval)); sv.append(int(sval))
            except ValueError:
                excluded += 1
        if len(gv) < 5:
            print(f"{c:<6}{len(gv):>4}{'too few':>10}{'-':>11}{excluded:>10}")
            continue
        kappa = cohen_kappa_score(gv, sv, weights="quadratic", labels=[1, 2, 3, 4, 5])
        within1 = sum(abs(a - b) <= 1 for a, b in zip(gv, sv)) / len(gv)
        kappas.append(kappa)
        print(f"{c:<6}{len(gv):>4}{kappa:>10.3f}{within1:>10.1%}{excluded:>10}")

    if kappas:
        print(f"\nMean quadratic-weighted kappa: {sum(kappas)/len(kappas):.3f}")
    print(f"System abstention rate: {sys_abstains}/{total_cells} = {sys_abstains/total_cells:.1%}")
    print("\nInterpretation guide: <0.20 slight | 0.21-0.40 fair | 0.41-0.60 moderate"
          " | 0.61-0.80 substantial | >0.80 almost perfect (Landis & Koch)")


if __name__ == "__main__":
    main()
