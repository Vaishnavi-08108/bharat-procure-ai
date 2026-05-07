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


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_money_value(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    digits_only = re.sub(r"[^\d]", "", raw_value)
    return int(digits_only) if digits_only else None


def _extract_section_lines(text: str, header: str, next_header: str | None = None) -> list[str]:
    section_pattern = header
    if next_header:
        section_pattern = rf"{header}(.*?){next_header}"
    else:
        section_pattern = rf"{header}(.*)"

    match = re.search(section_pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    section_text = match.group(1)
    lines = []
    for line in section_text.splitlines():
        stripped = line.strip(" \t-•")
        if stripped:
            lines.append(stripped)
    return lines


def _fallback_analyze_tender(text: str) -> dict:
    normalized_text = text.replace("\r", "\n")
    tender_title = None
    tender_id = _first_match(
        [
            r"TENDER\s*(?:NO|NUMBER)\s*[:\-]\s*([A-Z0-9\/\-]+)",
            r"REFERENCE\s*(?:NO|NUMBER)\s*[:\-]\s*([A-Z0-9\/\-]+)",
        ],
        normalized_text,
    )

    for line in normalized_text.splitlines():
        stripped = line.strip()
        if stripped:
            tender_title = stripped
            break

    turnover_raw = _first_match(
        [r"Minimum Annual Turnover\s*[:\-]?\s*Rs\.?\s*([\d,]+)\s*Lakhs?"],
        normalized_text,
    )
    emd_raw = _first_match(
        [
            r"Earnest Money Deposit\s*\(EMD\)\s*[:\-]?\s*Rs\.?\s*([\d,]+)",
            r"Earnest Money Deposit\s*[:\-]?\s*Rs\.?\s*([\d,]+)",
            r"\bEMD\b\s*[:\-]?\s*Rs\.?\s*([\d,]+)",
        ],
        normalized_text,
    )

    technical_requirements = _extract_section_lines(
        normalized_text,
        r"Technical Requirements\s*:\s*",
        r"Statutory Documents Required\s*:\s*",
    )
    statutory_documents = _extract_section_lines(
        normalized_text,
        r"Statutory Documents Required\s*:\s*",
        r"(?:\n\d+\.\d+\s+|\n\d+\.\s+|SCOPE OF WORK|EVALUATION CRITERIA)",
    )

    experience_requirement = None
    technical_requirements = [
        requirement
        for requirement in technical_requirements
        if not re.fullmatch(r"\d+(?:\.\d+)?", requirement)
    ]
    for requirement in technical_requirements:
        if "year" in requirement.lower():
            experience_requirement = requirement
            break

    return {
        "tender_title": tender_title or "Tender Document",
        "tender_id": tender_id,
        "financial_requirements": {
            "minimum_turnover_lakhs": _extract_money_value(turnover_raw),
            "earnest_money_deposit": _extract_money_value(emd_raw),
        },
        "technical_requirements": technical_requirements,
        "statutory_documents_required": statutory_documents,
        "experience_requirements": experience_requirement,
    }


def analyze_tender(text: str) -> dict:
    """
    Takes raw tender text and returns a structured checklist of requirements.
    Falls back to deterministic parsing when the model is unavailable.
    """
    fallback = _fallback_analyze_tender(text)
    if (
        fallback.get("technical_requirements")
        or fallback.get("statutory_documents_required")
        or fallback.get("financial_requirements", {}).get("minimum_turnover_lakhs") is not None
        or fallback.get("financial_requirements", {}).get("earnest_money_deposit") is not None
    ):
        return fallback

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return fallback

    model = genai.GenerativeModel("gemini-1.5-flash")

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

    try:
        response = model.generate_content(prompt)
        parsed = json.loads(_clean_model_json(response.text))
        if not parsed.get("tender_id") and fallback.get("tender_id"):
            parsed["tender_id"] = fallback["tender_id"]
        return parsed
    except Exception:
        return fallback
