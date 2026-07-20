# TrueScreen Golden-Set Rubric — v1.1, FROZEN 2026-07-20

**Amendment note (pre-labeling):** v1.0's provisional criteria are replaced with
the five criteria actually generated in `eval/frozen_rubric.json` from the
frozen JD, so human labels and system scores share identical criteria. No
labels were produced under v1.0. **Freeze clock starts now: no edits after the
first label is written.**

**Labeler:** one human (project author), all 50 resumes in manifest order,
against the frozen JD (`eval/frozen_jd.txt`, reproduced in v1.0 below) and the
five criteria below. Score each criterion 1-5, or `A` if unjudgeable.

## Criteria (from eval/frozen_rubric.json — verbatim ids, names, weights)

| ID | Criterion | Weight |
|----|-----------|--------|
| c1 | Professional Experience | 25 |
| c2 | Backend Programming Proficiency | 25 |
| c3 | Database Management | 20 |
| c4 | DevOps and Tooling | 15 |
| c5 | Educational Background | 15 |

## Score anchors

**c1 — Professional Experience** (years + closeness of roles to building
production software per the JD)
- 5: 2-5+ yrs in software development roles delivering applications/services
- 3: Technical professional experience but wrong specialization for the JD
  (e.g., pure testing, SAP config, network security) or unclear/short duration
- 1: No professional software-adjacent experience evident

**c2 — Backend Programming Proficiency** (Python/Java/C#/JS per JD)
- 5: Clear evidence of building with ≥1 JD language: named projects/systems,
  frameworks, not just a keyword list
- 3: JD language(s) listed but only as keywords, or adjacent programming only
  (scripting for testing, frontend-only JS, PL/SQL only)
- 1: No JD programming language evident

**c3 — Database Management** (SQL databases per JD)
- 5: Hands-on relational DB work evidenced (queries, schema, tuning; MySQL/
  PostgreSQL/SQL Server/Oracle)
- 3: DB mentioned among skills without usage evidence, or NoSQL/big-data only
  (Hadoop/Hive counts here, not 5)
- 1: No database signal

**c4 — DevOps and Tooling** (Git, CI/CD, cloud per JD)
- 5: ≥2 of {Git, CI/CD pipelines, cloud platforms} with usage evidence
- 3: One of them present, or tools listed without evidence
- 1: None evident

**c5 — Educational Background**
- 5: CS/IT or closely related degree (or strong equivalent-practice evidence)
- 3: Non-CS degree with technical coursework/certifications
- 1: No relevant education signal / none stated → prefer `A` if the section is
  entirely absent rather than weak

## Tiebreakers (apply in order)
1. Between two scores → "is there concrete EVIDENCE, not just a keyword?"
   No evidence → LOWER score.
2. CSV-extraction formatting damage does not lower any score; judge content.
3. Score against the frozen JD only, not the resume's own specialty.

## Abstain rule (human)
`A` for a criterion only when the resume gives no basis to judge it at all.
Note the reason in `labeler_notes`. Expected rare.

## Metric plan (declared before labeling)
Per-criterion quadratic-weighted Cohen's kappa (1-5 ordinal) + within-1
agreement %; mean kappa across c1-c5 as headline; system abstention rate
reported separately; `A` cells excluded pairwise with counts disclosed.

---
*v1.0 (provisional criteria + the frozen JD text) is retained in git history
for audit; the JD itself is unchanged and lives in `eval/frozen_jd.txt`.*
