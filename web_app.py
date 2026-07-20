"""
web_app.py — TrueScreen web demo (Flask).

Run locally:   python web_app.py        -> http://localhost:5000
Render deploy: gunicorn web_app:app    (see Procfile)

Routes:
  /            landing page
  /demo        the working screener (build rubric -> upload resume -> audit)
"""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap
OUT = Path("outputs")
RUBRIC_PATH = OUT / "rubric.json"

SAMPLE_JD = Path("sample_data/jd_fpna.md").read_text(encoding="utf-8") \
    if Path("sample_data/jd_it_support.md").exists() else ""

EVAL_BASELINE = {
    "within_1_agreement": "62.5%",
    "mae": "1.125",
    "abstention_rate": "20%",
    "finding": "The judge compresses scores toward 3 — it detects the presence "
               "of evidence but under-weighs its strength. Measured, published, "
               "and on the v2 roadmap.",
}


def load_rubric():
    if RUBRIC_PATH.exists():
        return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    return None


@app.errorhandler(413)
def too_large(e):
    return render_template("demo.html", rubric=load_rubric(), result=None,
                           error="File too large — resumes over 5 MB are not accepted.",
                           sample_jd=SAMPLE_JD), 413


@app.get("/")
def landing():
    return render_template("landing.html", eval_baseline=EVAL_BASELINE)


@app.get("/demo")
def demo():
    return render_template("demo.html", rubric=load_rubric(), result=None,
                           error=None, sample_jd=SAMPLE_JD)


@app.post("/build_rubric")
def build_rubric_route():
    jd_text = request.form.get("jd", "").strip()
    if len(jd_text) < 40:
        return render_template("demo.html", rubric=load_rubric(), result=None,
                               error="Paste a job description (at least a few lines).",
                               sample_jd=SAMPLE_JD)
    try:
        from agents.rubric_agent import build_rubric, save_rubric
        rubric = build_rubric(jd_text)
        OUT.mkdir(exist_ok=True)
        save_rubric(rubric, RUBRIC_PATH)
    except Exception as e:
        return render_template("demo.html", rubric=load_rubric(), result=None,
                               error=f"Rubric failed: {str(e)[:200]}",
                               sample_jd=SAMPLE_JD)
    return redirect(url_for("demo"))


@app.post("/score")
def score_route():
    rubric = load_rubric()
    if rubric is None:
        return render_template("demo.html", rubric=None, result=None,
                               error="Build a rubric first.", sample_jd=SAMPLE_JD)
    f = request.files.get("resume")
    if not f or not f.filename.lower().endswith(".pdf"):
        return render_template("demo.html", rubric=rubric, result=None,
                               error="Upload a PDF resume.", sample_jd=SAMPLE_JD)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        from agents.resume_parser import parse_resume, ScannedPDFError
        from agents.scoring_agent import score_resume
        try:
            parsed = parse_resume(tmp.name)
        except ScannedPDFError:
            return render_template(
                "demo.html", rubric=rubric, result=None,
                error="This looks like a scanned/image PDF — TrueScreen rejects "
                      "it honestly instead of guessing. Try a text-based PDF.",
                sample_jd=SAMPLE_JD)
        result = score_resume(parsed, rubric)
        result["filename"] = f.filename
        return render_template("demo.html", rubric=rubric, result=result,
                               error=None, sample_jd=SAMPLE_JD)
    except Exception as e:
        return render_template("demo.html", rubric=rubric, result=None,
                               error=f"Scoring failed: {str(e)[:200]}",
                               sample_jd=SAMPLE_JD)
    finally:
        os.unlink(tmp.name)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
