import google.generativeai as genai
import os, json
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def analyze_tender(text: str) -> dict:
    """
    Takes raw tender text and returns a structured checklist of requirements.
    """
    model = genai.GenerativeModel("gemini-1.5-flash")  # free tier model

    prompt = f"""
You are a government procurement expert. Read the following tender document text carefully.

Extract ALL mandatory requirements into a JSON object with this exact structure:
{{
  "tender_title": "string",
  "financial_requirements": {{
    "minimum_turnover_lakhs": number or null,
    "earnest_money_deposit": number or null
  }},
  "technical_requirements": [
    "requirement 1",
    "requirement 2"
  ],
  "statutory_documents_required": [
    "GST Certificate",
    "PAN Card",
    "etc"
  ],
  "experience_requirements": "string describing experience needed or null"
}}

Return ONLY valid JSON. No explanation. No markdown. Just the JSON.

TENDER TEXT:
{text[:8000]}
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Clean up in case Gemini adds markdown
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # If parsing fails, return a safe fallback
        return {
            "error": "Could not parse tender",
            "raw_response": raw
        }