import json
from rule_engine.verdict import generate_verdict

# 1. Load the raw dictionary for tender rules (Matches Member 1's format)
with open("rule_engine/mock_data/tender_rules.json") as f:
    tender_checklist = json.load(f)

# 2. Test all 3 bidder scenarios
for filename in ["bidder_pass.json", "bidder_fail.json", "bidder_hitl.json"]:
    with open(f"rule_engine/mock_data/{filename}") as f:
        # Load raw dictionary (Matches Member 1's format)
        bidder_data = json.load(f)

    # Use the new Bridge call: send list of dicts
    verdict = generate_verdict(
        tender_checklist=tender_checklist,
        bidder_documents=[bidder_data] 
    )

    print(f"\n{'='*50}")
    print(f"Bidder : {verdict.bidder_name}")
    print(f"Status : {verdict.overall_status.value}")
    print(f"Checks :")
    for check in verdict.checks:
        icon = "✅" if check.status == "PASS" else "❌" if check.status == "FAIL" else "⚠️"
        print(f"  {icon} {check.check_name}: {check.reason}")
    
    if verdict.audit_flags:
        print(f"Audit Flags:")
        for flag in verdict.audit_flags:
            print(f"  🚩 {flag}")
