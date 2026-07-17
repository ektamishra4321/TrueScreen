from agents.scoring_agent import verify_evidence, verify_evidence_detail

RESUME = """Ravi Kumar — IT Support Engineer
Managed Active Directory and GPO for a 250-seat office in Pune.
Resolved 40+ tickets weekly in Freshservice within SLA.
Automated onboarding with PowerShell scripts."""

# simulates pdfplumber reading across a two-column layout
INTERLEAVED = """Skills Machine Hardware Dreamweaver Outlook
Windows OS installation & Fireworks iLife
Repair Soundbooth Pages Mac OS Installation & Repair QuarkXpress"""


def test_exact_still_works():
    assert verify_evidence_detail(
        "Managed Active Directory and GPO for a 250-seat office", RESUME) == "exact"


def test_gapped_catches_column_interleaving():
    assert verify_evidence_detail(
        "Windows OS installation & Repair", INTERLEAVED) == "gapped"


def test_fabrication_still_fails():
    assert verify_evidence_detail("Led a team of 15 engineers at Google", RESUME) is None
    assert not verify_evidence("Led a team of 15 engineers at Google", RESUME)


def test_gapped_rejects_scattered_words():
    # words present but far apart / out of order must NOT verify
    assert verify_evidence_detail(
        "Repair Mac Windows installation OS", INTERLEAVED) is None


def test_short_quotes_never_gap_match():
    assert verify_evidence_detail("OS &", INTERLEAVED) is None
