"""
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
    print(f"\nSaved -> {OUT / 'rubric.json'}")


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
    print("\n=== RANKING ===")
    for r in ranked:
        print(f"  {r['total_score_0_5']:>5}  {Path(r['source']).name}  "
              f"({r['candidate'] or 'name not found'})")
    print(f"\nSaved -> {OUT / 'batch_results.json'} "
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
