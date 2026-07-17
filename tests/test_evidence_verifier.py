from agents.scoring_agent import verify_evidence

RESUME = """Ravi Kumar — IT Support Engineer
Managed Active Directory and GPO for a 250-seat office in Pune.
Resolved 40+ tickets weekly in Freshservice within SLA.
Automated onboarding with PowerShell scripts."""


def test_exact_quote_verifies():
    assert verify_evidence("Managed Active Directory and GPO for a 250-seat office", RESUME)


def test_whitespace_and_case_normalized():
    assert verify_evidence("managed   active directory AND gpo for a 250-seat office", RESUME)


def test_fabricated_quote_fails():
    assert not verify_evidence("Led a team of 15 engineers at Google", RESUME)


def test_paraphrase_fails():
    assert not verify_evidence("Handled AD and group policy for 250 seats", RESUME)


def test_too_short_quote_fails():
    assert not verify_evidence("SLA", RESUME)
