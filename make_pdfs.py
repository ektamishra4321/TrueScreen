"""Convert eval/golden50/*.txt to PDFs in eval/golden50_pdf/ for cli.py batch.
Run from the TrueScreen folder:
  pip install fpdf2
  python eval\\make_pdfs.py
"""
import os
import re
from fpdf import FPDF

SRC = os.path.join("eval", "golden50")
DST = os.path.join("eval", "golden50_pdf")
os.makedirs(DST, exist_ok=True)


def clean(text: str) -> str:
    # fix common UTF-8 mojibake, then keep printable ASCII only
    text = (text.replace("\u00e2\u0080\u00a2", " - ")   # broken bullet
                .replace("\u2022", " - ")
                .replace("\u00e2\u0080\u0093", "-")
                .replace("\u00e2\u0080\u0099", "'"))
    text = "".join(ch if (32 <= ord(ch) < 127 or ch == "\n") else " " for ch in text)
    text = re.sub(r"(\S{60})", r"\1 ", text)  # break unbroken 60+ char tokens
    return text


txts = sorted(f for f in os.listdir(SRC) if f.endswith(".txt"))
if not txts:
    raise SystemExit(f"No .txt files found in {SRC}")

for fn in txts:
    text = clean(open(os.path.join(SRC, fn), encoding="utf-8").read())
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.split("\n"):
        pdf.multi_cell(0, 5, line if line.strip() else " ", new_x="LMARGIN", new_y="NEXT")
    pdf.output(os.path.join(DST, fn.replace(".txt", ".pdf")))
    print(f"wrote {fn.replace('.txt', '.pdf')}")

print(f"\nDone: {len(txts)} PDFs in {DST}")
