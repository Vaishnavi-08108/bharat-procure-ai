import json, pytest
from rule_engine.schemas import TenderRequirements, BidderDocument
from rule_engine.verdict import generate_verdict

RULES = TenderRequirements(
    tender_id="CRPF-2024-001",
    min_turnover_lakhs=500.0,
    min_experience_years=3,
    required_certificates=["GST", "PAN", "MSME", "ISO_9001"],
    max_bid_validity_days=180,
    emd_required_lakhs=10.0
)

def load(filename):
    with open(f"rule_engine/mock_data/{filename}") as f:
        return BidderDocument(**json.load(f))

def test_pass_bidder():
    verdict = generate_verdict(load("bidder_pass.json"), RULES)
    assert verdict.overall_status == "PASS"
    assert verdict.audit_flags == []

def test_fail_bidder():
    verdict = generate_verdict(load("bidder_fail.json"), RULES)
    assert verdict.overall_status == "FAIL"

def test_hitl_bidder():
    verdict = generate_verdict(load("bidder_hitl.json"), RULES)
    assert verdict.overall_status == "HUMAN_REVIEW"
    assert len(verdict.audit_flags) > 0  # Address mismatch caught

def test_gst_pan_linkage():
    bidder = load("bidder_hitl.json")
    bidder.gst_number = "27XXXXXWRONG1ZZ"  # PAN not in GST
    verdict = generate_verdict(bidder, RULES)
    assert any("forgery" in f.lower() or "INTEGRITY" in f for f in verdict.audit_flags)