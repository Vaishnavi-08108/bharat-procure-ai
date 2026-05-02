import google.generativeai as genai
import os, json
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def audit_consistency(documents: list[dict]) -> dict:
    """
    Takes a list of extracted document data dicts.
    Checks if key fields (name, address, GST number etc.) 
    are consistent across all documents.
    
    Returns a report of matches, mismatches, and flags.
    """

    if not documents:
        return {"error": "No documents provided"}

    model = genai.GenerativeModel("gemini-1.5-flash")

    # Build a summary of all docs for Gemini to compare
    doc_summary = json.dumps(documents, indent=2)

    prompt = f"""
You are a government procurement auditor doing a cross-document verification.

Below are extracted fields from multiple documents submitted by a single bidder.
Your job is to find inconsistencies — like if the company name on the GST certificate 
is different from the PAN card, or if addresses don't match.

Documents:
{doc_summary}

Return ONLY a JSON object with this structure:
{{
  "overall_status": "CONSISTENT" or "INCONSISTENT" or "NEEDS_REVIEW",
  "checks": [
    {{
      "field": "entity_name",
      "status": "MATCH" or "MISMATCH" or "MISSING",
      "values_found": ["Name on GST", "Name on PAN"],
      "note": "brief explanation"
    }}
  ],
  "critical_flags": [
    "describe any serious mismatch here"
  ],
  "needs_human_review": true or false
}}

Return ONLY valid JSON. No markdown. No explanation.
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Clean markdown if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "overall_status": "NEEDS_REVIEW",
            "error": "Could not parse audit result",
            "raw_response": raw,
            "needs_human_review": True
        }