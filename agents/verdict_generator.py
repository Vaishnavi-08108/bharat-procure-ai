import json
import os
import re

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

from agents.rule_engine import (
    check_financial_requirements,
    check_statutory_documents,
)

load_dotenv()
if genai is not None:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def _clean_model_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _collect_bidder_data(documents: list[dict]) -> dict:
    bidder_data = {
        "entity_name": None,
        "annual_turnover_lakhs": None,
        "emd_amount": None,
        "experience_years": None,
    }

    for document in documents:
        key_fields = document.get("key_fields", {}) or {}
        if not bidder_data["entity_name"] and document.get("entity_name"):
            bidder_data["entity_name"] = document["entity_name"]
        for field_name in ("annual_turnover_lakhs", "emd_amount", "experience_years"):
            value = document.get(field_name, key_fields.get(field_name))
            if value is not None and bidder_data[field_name] is None:
                bidder_data[field_name] = value

    return bidder_data


def _document_matches_requirement(requirement: str, document: dict) -> bool:
    requirement_lower = requirement.lower()
    document_blob = " ".join(
        [
            str(document.get("document_type", "")),
            str(document.get("source_filename", "")),
            str(document.get("source_text_excerpt", "")),
        ]
    ).lower()

    keyword_groups = [
        ("gst", ["gst"]),
        ("pan", ["pan"]),
        ("msme", ["msme", "udyam"]),
        ("income tax", ["income tax", "itr"]),
        ("bank solvency", ["bank solvency"]),
        ("iso 9001", ["iso 9001"]),
        ("government", ["government", "crpf", "ministry"]),
        ("experience", ["experience", "contract duration"]),
    ]

    for anchor, synonyms in keyword_groups:
        if anchor in requirement_lower:
            return any(synonym in document_blob for synonym in synonyms)

    important_words = [
        word
        for word in re.findall(r"[a-z0-9]+", requirement_lower)
        if word not in {"must", "have", "valid", "minimum", "years", "required", "any", "the"}
    ]
    return any(word in document_blob for word in important_words)


def _technical_requirement_result(requirement: str, documents: list[dict], bidder_data: dict) -> dict:
    evidence_document = next(
        (document for document in documents if _document_matches_requirement(requirement, document)),
        None,
    )

    requirement_lower = requirement.lower()
    if "year" in requirement_lower:
        years_match = re.search(r"(\d+)", requirement)
        required_years = int(years_match.group(1)) if years_match else None
        bidder_years = bidder_data.get("experience_years")
        if required_years is not None and bidder_years is not None:
            if float(bidder_years) >= required_years:
                return {
                    "criterion": requirement,
                    "status": "MET",
                    "evidence": evidence_document.get("source_filename") if evidence_document else "Document text",
                    "note": f"Experience found: {bidder_years} years",
                }
            return {
                "criterion": requirement,
                "status": "NOT_MET",
                "evidence": evidence_document.get("source_filename") if evidence_document else "Missing evidence",
                "note": f"Experience only {bidder_years} years; {required_years} required",
            }

    if evidence_document:
        return {
            "criterion": requirement,
            "status": "MET",
            "evidence": evidence_document.get("source_filename") or evidence_document.get("document_type"),
            "note": "Matching supporting document found",
        }

    return {
        "criterion": requirement,
        "status": "CANNOT_VERIFY",
        "evidence": "No supporting document located",
        "note": "Upload additional evidence for this technical requirement",
    }


def _status_from_financial_rule(rule_status: str) -> str:
    return {
        "PASS": "MET",
        "FAIL": "NOT_MET",
        "CANNOT_VERIFY": "CANNOT_VERIFY",
    }.get(rule_status, "CANNOT_VERIFY")


def _status_from_statutory_rule(rule_status: str) -> str:
    return {
        "PRESENT": "MET",
        "MISSING": "NOT_MET",
        "EXPIRED": "NOT_MET",
    }.get(rule_status, "CANNOT_VERIFY")


def _fallback_verdict(
    tender_checklist: dict,
    bidder_documents: list[dict],
    audit_report: dict,
) -> dict:
    bidder_data = _collect_bidder_data(bidder_documents)
    financial_rules = check_financial_requirements(bidder_data, tender_checklist)
    statutory_rules = check_statutory_documents(bidder_documents, tender_checklist)

    criteria_results = []

    for result in statutory_rules.get("detailed_results", []):
        criteria_results.append(
            {
                "criterion": result["document"],
                "status": _status_from_statutory_rule(result["status"]),
                "evidence": "Submitted document" if result["status"] == "PRESENT" else "Not found",
                "note": result["note"],
            }
        )

    for result in financial_rules.get("detailed_results", []):
        criteria_results.append(
            {
                "criterion": result["check"],
                "status": _status_from_financial_rule(result["status"]),
                "evidence": str(result["found"]),
                "note": result["note"],
            }
        )

    for requirement in tender_checklist.get("technical_requirements", []):
        criteria_results.append(
            _technical_requirement_result(requirement, bidder_documents, bidder_data)
        )

    human_review_items = []
    for document in bidder_documents:
        if document.get("needs_human_review"):
            label = document.get("source_filename") or document.get("document_type") or "Document"
            human_review_items.append(f"Manual review required for {label}")

    if audit_report.get("overall_status") in {"INCONSISTENT", "NEEDS_REVIEW"}:
        human_review_items.extend(audit_report.get("critical_flags", []))

    for item in criteria_results:
        if item["status"] == "CANNOT_VERIFY":
            human_review_items.append(f"Could not verify: {item['criterion']}")

    disqualification_reasons = [
        f"{item['criterion']}: {item['note']}"
        for item in criteria_results
        if item["status"] == "NOT_MET"
    ]

    met_count = sum(1 for item in criteria_results if item["status"] == "MET")
    total_count = len(criteria_results)
    score_percent = round((met_count / total_count) * 100) if total_count else 0

    if audit_report.get("overall_status") == "INCONSISTENT":
        verdict = "REFER_TO_COMMITTEE"
    elif disqualification_reasons:
        verdict = "FAIL"
    elif human_review_items:
        verdict = "REFER_TO_COMMITTEE"
    else:
        verdict = "PASS"

    summary = (
        f"{bidder_data.get('entity_name') or 'Bidder'} scored {score_percent}% "
        f"across {total_count} evaluated checks. Verdict: {verdict}."
    )

    return {
        "bidder_verdict": verdict,
        "score_percent": score_percent,
        "criteria_results": criteria_results,
        "disqualification_reasons": disqualification_reasons,
        "human_review_items": list(dict.fromkeys(human_review_items)),
        "summary": summary,
        "supporting_checks": {
            "financial_rules": financial_rules,
            "statutory_rules": statutory_rules,
        },
    }


def generate_verdict(
    tender_checklist: dict,
    bidder_documents: list[dict],
    audit_report: dict,
) -> dict:
    """
    Final agent that compares the tender requirements with bidder evidence.
    Falls back to deterministic evaluation when the model is unavailable.
    """
    fallback = _fallback_verdict(tender_checklist, bidder_documents, audit_report)
    if fallback.get("criteria_results"):
        return fallback

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return fallback

    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
You are the final evaluation officer for a government tender.

You have:
1. The tender requirements checklist
2. The bidder's submitted documents (already extracted)
3. A consistency audit report

Your job: For each requirement in the checklist, determine if the bidder
has met it or not, based on the submitted documents.

TENDER CHECKLIST:
{json.dumps(tender_checklist, indent=2)}

BIDDER DOCUMENTS DATA:
{json.dumps(bidder_documents, indent=2)}

CONSISTENCY AUDIT:
{json.dumps(audit_report, indent=2)}

Return ONLY a JSON object:
{{
  "bidder_verdict": "PASS" or "FAIL" or "REFER_TO_COMMITTEE",
  "score_percent": 0-100,
  "criteria_results": [
    {{
      "criterion": "name of requirement",
      "status": "MET" or "NOT_MET" or "PARTIALLY_MET" or "CANNOT_VERIFY",
      "evidence": "which document proved this",
      "note": "brief explanation"
    }}
  ],
  "disqualification_reasons": [
    "reason 1 if FAIL"
  ],
  "human_review_items": [
    "items that need officer attention"
  ],
  "summary": "2 sentence plain English summary of the verdict"
}}

IMPORTANT RULES:
- If consistency audit shows INCONSISTENT, verdict must be REFER_TO_COMMITTEE
- If any mandatory document is missing, verdict is FAIL
- If confidence of any document was below 0.85, add it to human_review_items
- Never disqualify based on unverifiable info; mark as CANNOT_VERIFY instead

Return ONLY valid JSON. No markdown.
"""

    try:
        result = json.loads(_clean_model_json(model.generate_content(prompt).text))
        if "supporting_checks" not in result:
            result["supporting_checks"] = fallback["supporting_checks"]
        return result
    except Exception:
        return fallback
