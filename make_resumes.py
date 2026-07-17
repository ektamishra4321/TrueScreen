"""
make_resumes.py — build sample resume PDFs from the Kaggle Resume.csv

Usage:
    python make_resumes.py --csv Resume.csv --n 5
Writes N INFORMATION-TECHNOLOGY resumes as PDFs into data/resumes/.
Requires: pip install fpdf2
"""
import argparse
import csv
import sys
from pathlib import Path

from fpdf import FPDF

csv.field_size_limit(10_000_000)  # resume text cells are huge


def text_to_pdf(text: str, out_path: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    # Helvetica is latin-1 only; replace anything it can't print
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    for line in safe.splitlines():
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w=0, h=5, text=line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(out_path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to Resume.csv")
    ap.add_argument("--category", default="INFORMATION-TECHNOLOGY")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out", default="data/resumes")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    made = 0
    with open(args.csv, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        cols = {c.lower(): c for c in reader.fieldnames}
        id_col = cols.get("id", reader.fieldnames[0])
        text_col = cols.get("resume_str")
        cat_col = cols.get("category")
        if not text_col or not cat_col:
            print(f"Unexpected columns: {reader.fieldnames}")
            sys.exit(1)
        for row in reader:
            if row[cat_col].strip().upper() != args.category.upper():
                continue
            text = row[text_col].strip()
            if len(text) < 500:   # skip near-empty entries
                continue
            out_path = out_dir / f"IT_{row[id_col]}.pdf"
            text_to_pdf(text, out_path)
            made += 1
            print(f"  wrote {out_path}")
            if made >= args.n:
                break
    print(f"\n{made} PDFs written to {out_dir}")
    if made == 0:
        print("No matching rows found — check --category spelling.")


if __name__ == "__main__":
    main()
