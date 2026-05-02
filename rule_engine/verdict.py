from datetime import datetime, timezone
from .schemas import (
    TenderRequirements, BidderDocument, BidderVerdict, VerdictStatus
)
from .evaluator import run_all_checks
from .auditor import run_cross_document_audit

def generate_verdict(
    bidder: BidderDocument,
    rules: TenderRequirements,
    model_version: str = "1.0.0"
) -> BidderVerdict:

    checks = run_all_checks(bidder, rules)
    audit_flags = run_cross_document_audit(bidder)

    # Determine overall status:
    # Any FAIL → overall FAIL
    # Any HUMAN_REVIEW (and no FAIL) → overall HUMAN_REVIEW
    # All PASS → overall PASS
    statuses = [c.status for c in checks]

    if VerdictStatus.FAIL in statuses:
        overall = VerdictStatus.FAIL
    elif VerdictStatus.HUMAN_REVIEW in statuses or len(audit_flags) > 0:
        overall = VerdictStatus.HUMAN_REVIEW
    else:
        overall = VerdictStatus.PASS

    return BidderVerdict(
        bidder_id=bidder.bidder_id,
        bidder_name=bidder.bidder_name,
        overall_status=overall,
        checks=checks,
        audit_flags=audit_flags,
        model_version=model_version,
        timestamp=datetime.now(timezone.utc).isoformat()
    )