# TrueScreen Golden-Set Rubric — FROZEN 2026-07-20

**Freeze rule:** No edits to this file after labeling begins. If a rule proves
ambiguous mid-labeling, note the case in `labeler_notes`, finish labeling under
the rule as written, and propose changes only for a future v2 rubric.

**Labeler:** one human (project author). All 50 resumes labeled in one or two
sittings, in manifest order, against the single JD below.

---

## Frozen Job Description (score every resume against THIS, verbatim)

> **Software Engineer (Backend / Full-stack) — 2-5 years**
> We are hiring a software engineer to build and maintain production web
> services. Responsibilities: design and implement APIs and backend services;
> write clean, tested, maintainable code; work with relational databases;
> deploy and monitor services in production; collaborate with product and QA.
> Requirements: 2-5 years professional software development experience;
> strong programming skills in at least one of Python / Java / C# / JavaScript;
> experience with SQL databases; familiarity with version control (Git) and
> CI/CD; exposure to cloud platforms (AWS/Azure/GCP) is a plus; a degree in
> CS/IT or equivalent practical experience.

---

## Criteria and weights

| ID | Criterion | Weight |
|----|-----------|--------|
| c1 | Core technical skills match (languages, DBs, tools vs JD) | 0.30 |
| c2 | Relevant experience depth (years + closeness of roles to JD) | 0.30 |
| c3 | Project / impact evidence (concrete deliverables, outcomes) | 0.20 |
| c4 | Education & certifications (relevance to role) | 0.10 |
| c5 | Resume quality (structure, clarity, specificity) | 0.10 |

## Score anchors (1-5, per criterion)

**c1 — Core technical skills**
- 5: ≥2 required skills (Python/Java/C#/JS, SQL, Git/CI) with usage evidence, not just a keyword list
- 3: 1-2 required skills present but mostly as keywords, or adjacent stack (e.g., only frontend, only SAP)
- 1: No required skills; unrelated stack

**c2 — Relevant experience depth**
- 5: 2-5+ yrs in software development roles building services/applications
- 3: Some dev experience but wrong specialization or unclear duration; or <2 yrs
- 1: No professional software development experience

**c3 — Project / impact evidence**
- 5: ≥2 concrete projects/deliverables with specifics (what was built, tech, outcome/metric)
- 3: Projects mentioned but generic (responsibilities listed, no outcomes)
- 1: No project detail at all

**c4 — Education & certifications**
- 5: CS/IT degree or strong relevant certification
- 3: Non-CS degree with some technical coursework/certs
- 1: No relevant education signal

**c5 — Resume quality**
- 5: Well structured, specific, scannable
- 3: Readable but padded/vague in places
- 1: Disorganized, heavy boilerplate, hard to extract facts

## Tiebreakers (apply in order)
1. Between two scores → ask "is there concrete EVIDENCE, not just a keyword?"
   No evidence → take the LOWER score.
2. Dataset artifacts (broken formatting from CSV extraction) do NOT reduce c5
   below 3 by themselves; judge the underlying content.
3. Score against the frozen JD only — a brilliant DevOps resume still scores
   what the JD says, not what a DevOps JD would say.

## Abstain rule (human)
If a criterion is genuinely unjudgeable from the text (e.g., education section
entirely missing), write `A` instead of a number for that criterion and note
why. Expected to be rare.

## Metric plan (declared before labeling)
- Per-criterion quadratic-weighted Cohen's kappa (human vs system), 1-5 ordinal
- Per-criterion within-1 agreement %
- Overall: mean kappa across c1-c5; system abstention rate reported separately
- `A` cells excluded pairwise from kappa; count reported
