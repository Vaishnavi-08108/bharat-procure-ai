import google.generativeai as genai
import os, json
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def generate_verdict(
    tender_checklist: dict,
    bidder_documents: list[dict],
    audit_report: dict
) -> dict:
    """
    Final agent — compares everything and gives a verdict.
    
    tender_checklist: output from tender_analyst
    bidder_documents: list of outputs from vision_specialist
    audit_report: output from consistency_auditor
    
    Returns final PASS/FAIL verdict with reasons for each criterion.
    """

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
- Never disqualify based on unverifiable info — mark as CANNOT_VERIFY instead

Return ONLY valid JSON. No markdown.
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        result = json.loads(raw)
        return result
    except json.JSONDecodeError:
        return {
            "bidder_verdict": "REFER_TO_COMMITTEE",
            "error": "Could not parse verdict",
            "raw_response": raw,
            "needs_human_review": True
        }