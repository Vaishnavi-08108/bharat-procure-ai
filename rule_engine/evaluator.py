from typing import List
from .schemas import (
    TenderRequirements, BidderDocument, CheckResult, VerdictStatus
)

CONFIDENCE_THRESHOLD = 0.85

def _status_from_confidence(passed: bool, confidence: float) -> VerdictStatus:
    """Core guard: low confidence → HUMAN_REVIEW, never auto-FAIL."""
    if confidence < CONFIDENCE_THRESHOLD:
        return VerdictStatus.HUMAN_REVIEW
    return VerdictStatus.PASS if passed else VerdictStatus.FAIL

def check_turnover(bidder: BidderDocument, rules: TenderRequirements) -> CheckResult:
    if bidder.annual_turnover_lakhs is None:
        return CheckResult(
            check_name="Annual Turnover",
            status=VerdictStatus.HUMAN_REVIEW,
            reason="Turnover value could not be extracted from documents",
            required_value=f"≥ Rs. {rules.min_turnover_lakhs} lakhs",
            confidence=0.0
        )
    passed = bidder.annual_turnover_lakhs >= rules.min_turnover_lakhs
    status = _status_from_confidence(passed, bidder.turnover_confidence)
    return CheckResult(
        check_name="Annual Turnover",
        status=status,
        reason=(
            f"Turnover Rs. {bidder.annual_turnover_lakhs}L meets requirement"
            if passed else
            f"Turnover Rs. {bidder.annual_turnover_lakhs}L below required Rs. {rules.min_turnover_lakhs}L"
        ),
        extracted_value=f"Rs. {bidder.annual_turnover_lakhs} lakhs",
        required_value=f"≥ Rs. {rules.min_turnover_lakhs} lakhs",
        confidence=bidder.turnover_confidence
    )

def check_experience(bidder: BidderDocument, rules: TenderRequirements) -> CheckResult:
    if bidder.years_of_experience is None:
        return CheckResult(
            check_name="Work Experience",
            status=VerdictStatus.HUMAN_REVIEW,
            reason="Experience could not be extracted",
            required_value=f"≥ {rules.min_experience_years} years",
            confidence=0.0
        )
    passed = bidder.years_of_experience >= rules.min_experience_years
    status = _status_from_confidence(passed, bidder.experience_confidence)
    return CheckResult(
        check_name="Work Experience",
        status=status,
        reason=(
            f"{bidder.years_of_experience} years meets requirement"
            if passed else
            f"{bidder.years_of_experience} years is below required {rules.min_experience_years} years"
        ),
        extracted_value=f"{bidder.years_of_experience} years",
        required_value=f"≥ {rules.min_experience_years} years",
        confidence=bidder.experience_confidence
    )

def check_certificates(bidder: BidderDocument, rules: TenderRequirements) -> List[CheckResult]:
    results = []
    for cert in rules.required_certificates:
        present = bidder.certificates_present.get(cert, False)
        results.append(CheckResult(
            check_name=f"Certificate: {cert}",
            status=VerdictStatus.PASS if present else VerdictStatus.FAIL,
            reason=f"{cert} certificate {'found' if present else 'NOT found'} in submission",
            extracted_value="Present" if present else "Missing",
            required_value="Mandatory",
            confidence=1.0
        ))
    return results

def check_emd(bidder: BidderDocument, rules: TenderRequirements) -> CheckResult:
    if bidder.emd_submitted_lakhs is None:
        return CheckResult(
            check_name="EMD Submission",
            status=VerdictStatus.FAIL,
            reason="EMD document not found in submission",
            required_value=f"Rs. {rules.emd_required_lakhs} lakhs"
        )
    passed = bidder.emd_submitted_lakhs >= rules.emd_required_lakhs
    return CheckResult(
        check_name="EMD Submission",
        status=VerdictStatus.PASS if passed else VerdictStatus.FAIL,
        reason=(
            f"EMD of Rs. {bidder.emd_submitted_lakhs}L submitted correctly"
            if passed else
            f"EMD Rs. {bidder.emd_submitted_lakhs}L is below required Rs. {rules.emd_required_lakhs}L"
        ),
        extracted_value=f"Rs. {bidder.emd_submitted_lakhs} lakhs",
        required_value=f"Rs. {rules.emd_required_lakhs} lakhs"
    )

def run_all_checks(bidder: BidderDocument, rules: TenderRequirements) -> List[CheckResult]:
    checks = []
    checks.append(check_turnover(bidder, rules))
    checks.append(check_experience(bidder, rules))
    checks.extend(check_certificates(bidder, rules))
    checks.append(check_emd(bidder, rules))
    return checks
