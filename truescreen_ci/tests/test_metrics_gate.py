"""CI gate: the eval pipeline itself must be correct and deterministic.
Verifies (1) metrics_kappa computes known-answer kappa values, and
(2) results_to_csv converts a fixture batch_results.json correctly.
No API keys, no network.
"""
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(args, cwd=ROOT):
    return subprocess.run([sys.executable] + args, cwd=cwd,
                          capture_output=True, text=True)


def test_kappa_perfect_agreement(tmp_path):
    """Identical golden and system scores must give kappa 1.0 everywhere."""
    rows = [["id", "c1", "c2", "c3", "c4", "c5"]]
    for i in range(1, 21):
        rows.append([f"resume_{i:02d}", 1 + i % 5, 1 + (i + 1) % 5,
                     1 + (i + 2) % 5, 1 + (i + 3) % 5, 1 + (i + 4) % 5])
    g = tmp_path / "g.csv"
    s = tmp_path / "s.csv"
    for p in (g, s):
        with open(p, "w", newline="") as f:
            csv.writer(f).writerows(rows)
    r = run([os.path.join("eval", "metrics_kappa.py"),
             "--golden", str(g), "--system", str(s)])
    assert r.returncode == 0, r.stderr
    assert "Mean quadratic-weighted kappa: 1.000" in r.stdout


def test_kappa_handles_abstain(tmp_path):
    """'A' cells must be excluded, and abstention rate reported."""
    header = ["id", "c1", "c2", "c3", "c4", "c5"]
    grows = [header] + [[f"r{i}", 3, 3, 3, 3, 3] for i in range(20)]
    srows = [header] + [[f"r{i}", 3, 3, 3, 3, "A" if i < 2 else 3]
                        for i in range(20)]
    g, s = tmp_path / "g.csv", tmp_path / "s.csv"
    with open(g, "w", newline="") as f:
        csv.writer(f).writerows(grows)
    with open(s, "w", newline="") as f:
        csv.writer(f).writerows(srows)
    r = run([os.path.join("eval", "metrics_kappa.py"),
             "--golden", str(g), "--system", str(s)])
    assert r.returncode == 0, r.stderr
    assert "System abstention rate: 2/100" in r.stdout


def test_results_converter(tmp_path):
    """Fixture batch_results.json must convert to the expected CSV shape."""
    fixture = [
        {"source": "eval/golden50_pdf/resume_01.pdf",
         "per_criterion": [
             {"criterion_id": "c1", "score": 4, "status": "ok"},
             {"criterion_id": "c2", "score": 2.6, "status": "ok"},
             {"criterion_id": "c3", "score": None, "status": "abstained"},
             {"criterion_id": "c4", "score": 1, "status": "ok"},
             {"criterion_id": "c5", "score": 5, "status": "ok"},
         ]},
    ]
    outdir = tmp_path / "outputs"
    evaldir = tmp_path / "eval"
    outdir.mkdir()
    evaldir.mkdir()
    (outdir / "batch_results.json").write_text(json.dumps(fixture))
    # copy the converter into the sandbox layout it expects
    conv_src = open(os.path.join(ROOT, "eval", "results_to_csv.py")).read()
    (evaldir / "results_to_csv.py").write_text(conv_src)
    r = subprocess.run([sys.executable, str(evaldir / "results_to_csv.py")],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = list(csv.reader(open(evaldir / "system_scores_50.csv")))
    assert out[0] == ["id", "c1", "c2", "c3", "c4", "c5"]
    assert out[1] == ["resume_01", "4", "3", "A", "1", "5"]  # 2.6 rounds to 3
