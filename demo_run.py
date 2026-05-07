import json
from rule_engine.schemas import TenderRequirements, BidderDocument
from rule_engine.verdict import generate_verdict

# Load tender rules
with open("rule_engine/mock_data/tender_rules.json") as f:
    rules = TenderRequirements(**json.load(f))

# Test all 3 bidder scenarios
for filename in ["bidder_pass.json", "bidder_fail.json", "bidder_hitl.json"]:
    with open(f"rule_engine/mock_data/{filename}") as f:
        bidder = BidderDocument(**json.load(f))

    verdict = generate_verdict(bidder, rules)

    print(f"\n{'='*50}")
    print(f"Bidder : {verdict.bidder_name}")
    print(f"Status : {verdict.overall_status.value}"
    )
    print(f"Checks :")
    for check in verdict.checks:
        icon = "✅" if check.status == "PASS" else "❌" if check.status == "FAIL" else "⚠️"
        print(f"  {icon} {check.check_name}: {check.reason}")
    if verdict.audit_flags:
        print(f"Audit Flags:")
        for flag in verdict.audit_flags:
            print(f"  🚩 {flag}")