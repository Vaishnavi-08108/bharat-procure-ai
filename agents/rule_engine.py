"""
MEMBER 2 — Rule Engine
Deterministic (pure math/logic) validation.
No AI used here — just Python if/else for financial 
and technical threshold checks.
This is intentional: numbers should never be left to AI judgment.
"""

from datetime import datetime
import re


def _normalize_doc_label(value: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", value.lower())
    cleaned = cleaned.replace("certificate", "")
    cleaned = cleaned.replace("card", "")
    cleaned = cleaned.replace("of the firm", "")
    cleaned = cleaned.replace("mandatory", "")
    cleaned = cleaned.replace("if applicable", "")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return cleaned.strip()


def check_financial_requirements(
    bidder_data: dict,
    tender_checklist: dict
) -> dict:
    """
    Checks financial thresholds deterministically.
    
    bidder_data: extracted fields from bidder documents
    tender_checklist: output from tender_analyst agent
    
    Returns pass/fail for each financial criterion.
    """
    results = []
    flags = []

    financial_reqs = tender_checklist.get(
        "financial_requirements", {}
    )

    # ── Check 1: Minimum Turnover ──
    required_turnover = financial_reqs.get(
        "minimum_turnover_lakhs"
    )
    bidder_turnover = bidder_data.get(
        "annual_turnover_lakhs"
    )

    if required_turnover is not None:
        if bidder_turnover is None:
            results.append({
                "check": "Minimum Annual Turnover",
                "required": f"₹{required_turnover} Lakhs",
                "found": "NOT PROVIDED",
                "status": "CANNOT_VERIFY",
                "note": "Turnover data missing from documents"
            })
            flags.append("Turnover document missing or unreadable")
        elif float(bidder_turnover) >= float(required_turnover):
            results.append({
                "check": "Minimum Annual Turnover",
                "required": f"₹{required_turnover} Lakhs",
                "found": f"₹{bidder_turnover} Lakhs",
                "status": "PASS",
                "note": f"Exceeds requirement by "
                        f"₹{float(bidder_turnover) - float(required_turnover):.1f}L"
            })
        else:
            results.append({
                "check": "Minimum Annual Turnover",
                "required": f"₹{required_turnover} Lakhs",
                "found": f"₹{bidder_turnover} Lakhs",
                "status": "FAIL",
                "note": f"Short by "
                        f"₹{float(required_turnover) - float(bidder_turnover):.1f}L"
            })
            flags.append(
                f"Turnover ₹{bidder_turnover}L below required ₹{required_turnover}L"
            )

    # ── Check 2: EMD (Earnest Money Deposit) ──
    required_emd = financial_reqs.get("earnest_money_deposit")
    bidder_emd = bidder_data.get("emd_amount")

    if required_emd is not None:
        if bidder_emd is None:
            results.append({
                "check": "Earnest Money Deposit",
                "required": f"₹{required_emd}",
                "found": "NOT PROVIDED",
                "status": "FAIL",
                "note": "EMD proof document missing — mandatory disqualification"
            })
            flags.append("EMD proof not submitted — mandatory requirement")
        elif float(bidder_emd) >= float(required_emd):
            results.append({
                "check": "Earnest Money Deposit",
                "required": f"₹{required_emd}",
                "found": f"₹{bidder_emd}",
                "status": "PASS",
                "note": "EMD amount verified"
            })
        else:
            results.append({
                "check": "Earnest Money Deposit",
                "required": f"₹{required_emd}",
                "found": f"₹{bidder_emd}",
                "status": "FAIL",
                "note": "EMD amount insufficient"
            })
            flags.append(f"EMD ₹{bidder_emd} below required ₹{required_emd}")

    # ── Check 3: Experience Years ──
    exp_req = tender_checklist.get("experience_requirements", "")
    bidder_exp = bidder_data.get("experience_years")

    if exp_req and bidder_exp is not None:
        # Extract number from requirement string like "3 years"
        import re
        years_needed = re.search(r'\d+', str(exp_req))
        if years_needed:
            years_needed = int(years_needed.group())
            if int(bidder_exp) >= years_needed:
                results.append({
                    "check": "Experience Requirement",
                    "required": f"{years_needed} years",
                    "found": f"{bidder_exp} years",
                    "status": "PASS",
                    "note": "Experience requirement met"
                })
            else:
                results.append({
                    "check": "Experience Requirement",
                    "required": f"{years_needed} years",
                    "found": f"{bidder_exp} years",
                    "status": "FAIL",
                    "note": f"Short by {years_needed - int(bidder_exp)} years"
                })
                flags.append(
                    f"Experience {bidder_exp}yr below required {years_needed}yr"
                )

    # ── Final summary ──
    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]

    return {
        "financial_check_summary": {
            "total_checks": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "overall": "FAIL" if failed else "PASS"
        },
        "detailed_results": results,
        "disqualification_flags": flags
    }


def check_statutory_documents(
    extracted_docs: list,
    tender_checklist: dict
) -> dict:
    """
    Checks if all mandatory statutory documents are present.
    
    extracted_docs: list of dicts from vision_specialist
    tender_checklist: output from tender_analyst
    
    Returns which documents are present, missing, or expired.
    """
    required_docs = tender_checklist.get(
        "statutory_documents_required", []
    )

    # Build a map of what we found
    found_doc_types = []
    for doc in extracted_docs:
        doc_type = doc.get("document_type", "").lower()
        found_doc_types.append(doc_type)

    results = []
    missing = []

    for req_doc in required_docs:
        req_lower = _normalize_doc_label(req_doc)

        # Check if any extracted doc matches
        matched = any(
            req_lower in _normalize_doc_label(found)
            or _normalize_doc_label(found) in req_lower
            for found in found_doc_types
        )

        if matched:
            # Find the matching doc to check validity
            matching_doc = next(
                (d for d in extracted_docs
                 if req_lower in _normalize_doc_label(d.get("document_type", ""))
                 or _normalize_doc_label(d.get("document_type", "")) in req_lower),
                None
            )

            # Check expiry if available
            validity = None
            if matching_doc:
                validity = matching_doc.get("validity_date")
                doc_type = matching_doc.get("document_type", "").lower()
                status_text = str(matching_doc.get("key_fields", {}).get("status", "")).lower()

            status = "PRESENT"
            note = "Document found and verified"

            # Simple expiry check
            should_check_expiry = any(
                keyword in doc_type
                for keyword in ["solvency", "license", "permit", "iso", "clearance"]
            )
            if "expired" in status_text or "inactive" in status_text:
                status = "EXPIRED"
                note = f"Document status is {status_text}"
                missing.append(f"{req_doc} â€” EXPIRED")
            elif validity and should_check_expiry:
                try:
                    # Try common date formats
                    for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"]:
                        try:
                            exp_date = datetime.strptime(validity, fmt)
                            if exp_date < datetime.now():
                                status = "EXPIRED"
                                note = f"Document expired on {validity}"
                                missing.append(f"{req_doc} — EXPIRED")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            results.append({
                "document": req_doc,
                "status": status,
                "note": note
            })
        else:
            results.append({
                "document": req_doc,
                "status": "MISSING",
                "note": "Document not found in submission"
            })
            missing.append(req_doc)

    return {
        "statutory_check_summary": {
            "total_required": len(required_docs),
            "found": len(required_docs) - len(missing),
            "missing_or_expired": len(missing),
            "overall": "FAIL" if missing else "PASS"
        },
        "detailed_results": results,
        "missing_documents": missing
    }
