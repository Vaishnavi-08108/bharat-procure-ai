from datetime import datetime, timezone
from typing import List, Dict, Any
from .schemas import (
    TenderRequirements, BidderDocument, BidderVerdict, VerdictStatus
)
from .evaluator import run_all_checks
from .auditor import run_cross_document_audit

def generate_verdict(
    tender_checklist: Dict[str, Any],
    bidder_documents: List[Dict[str, Any]],
    audit_report: Dict[str, Any] = None,
    model_version: str = "1.0.0"
) -> BidderVerdict:
    # 1. Convert Member 1's dicts into your Pydantic objects
    rules = TenderRequirements(**tender_checklist)
    
    merged_data = {"certificates_present": {}}
    for doc in bidder_documents:
        merged_data.update(doc)
        doc_type = doc.get("doc_type", "").upper()
        if doc_type:
            merged_data["certificates_present"][doc_type] = True

    # Use .get() or provide defaults to avoid validation errors
    if "bidder_id" not in merged_data: merged_data["bidder_id"] = "UNKNOWN"
    if "bidder_name" not in merged_data: merged_data["bidder_name"] = "Unknown Bidder"

    bidder = BidderDocument(**merged_data)

    # 2. Run Engine Logic
    checks = run_all_checks(bidder, rules)
    
    # 3. Use Audit data
    audit_flags = audit_report.get("flags", []) if audit_report else run_cross_document_audit(bidder)

    # 4. Final Verdict Determination
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
