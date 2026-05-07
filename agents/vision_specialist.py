import base64
import io
import json
import os
import re

import PyPDF2
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

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


def enhance_image(image_bytes: bytes) -> bytes:
    """
    Uses OpenCV to fix blurry/skewed photos from mobile cameras.
    Returns cleaned image bytes.
    """
    if cv2 is None or np is None:
        return image_bytes

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return image_bytes

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(denoised, -1, kernel)
    enhanced = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    _, buffer = cv2.imencode(".png", enhanced)
    return buffer.tobytes()


def _clean_model_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _extract_pdf_text(document_bytes: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(document_bytes))
    except Exception:
        return ""

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r", "\n")).strip()


def _parse_indian_amount(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw_value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _infer_document_type(text: str, doc_type: str, filename: str | None) -> str:
    source = f"{doc_type} {filename or ''} {text[:500]}".lower()
    document_map = [
        ("GST Registration Certificate", [r"\bgst\b", r"\bgstin\b", r"goods and services tax"]),
        ("MSME Registration Certificate", [r"\bmsme\b", r"\budyam\b"]),
        ("PAN Card", [r"\bpan\b", r"permanent account number"]),
        ("Income Tax Return", [r"income tax", r"\bitr\b"]),
        ("Bank Solvency Certificate", [r"bank solvency"]),
        ("EMD Deposit Proof", [r"\bemd\b", r"earnest money"]),
        ("Experience Certificate", [r"experience", r"contract duration", r"to whomsoever it may concern"]),
        ("ISO 9001:2015 Certificate", [r"iso 9001"]),
    ]
    for label, patterns in document_map:
        if any(re.search(pattern, source) for pattern in patterns):
            return label
    return doc_type.replace("_", " ").title() if doc_type else "Certificate"


def _extract_address(text: str) -> str | None:
    return _first_match(
        [
            r"Address\s*[:\-]\s*(.+?)(?=\s+(?:Date of Registration|Status|Category|Major Activity|Type of Taxpayer)\s*:|$)",
            r"Registered Address\s*[:\-]\s*(.+?)(?=\s+(?:Date of Registration|Status|Category|Major Activity)\s*:|$)",
            r"Father's Name\s*/\s*Registered Address\s*[:\-]\s*(.+?)(?=\s+(?:Date of Registration|Status|Category)\s*:|$)",
        ],
        text,
    )


def _clean_entity_name(candidate: str | None) -> str | None:
    if not candidate:
        return None

    cleaned = re.sub(r"\s+", " ", candidate).strip(" :;-_")
    lowered = cleaned.lower()
    invalid_labels = {
        "date of birth",
        "date of birth:",
        "dob",
        "father's name",
        "father name",
        "address",
        "type",
        "status",
        "name",
        "trade name",
        "legal name",
    }
    invalid_phrases = (
        "standard bidding document",
        "procurement of civil works",
        "government of india",
        "instructions to bidders",
        "date of birth",
    )

    if not cleaned or cleaned in {"_", "__", "___"}:
        return None
    if lowered in invalid_labels or any(phrase in lowered for phrase in invalid_phrases):
        return None
    if cleaned.endswith(":") or not re.search(r"[A-Za-z0-9]", cleaned):
        return None
    return cleaned


def _extract_entity_name(text: str) -> str | None:
    candidate = _first_match(
        [
            r"Legal Name\s*[:\-]\s*(.+?)(?=\s+(?:Trade Name|Address|Date of Registration|Date of Birth|Status)\s*:|$)",
            r"Name of Enterprise\s*[:\-]\s*(.+?)(?=\s+(?:Type|Address|Date of Registration|Date of Birth|Category)\s*:|$)",
            r"Trade Name\s*[:\-]\s*(.+?)(?=\s+(?:Address|Date of Registration|Date of Birth|Status)\s*:|$)",
            r"Name\s*[:\-]\s*(.+?)(?=\s+(?:Date of Incorporation|Date of Birth|DOB|Father's Name|Address|Type)\s*:|$)",
            r"M/s\s+([A-Za-z0-9&.,() \-]+)",
        ],
        text,
    )
    return _clean_entity_name(candidate)


def _extract_registration_number(text: str, document_type: str) -> str | None:
    if "GST" in document_type.upper():
        return _first_match([r"GSTIN\s*[:\-]\s*([A-Z0-9]+)"], text)
    if "PAN" in document_type.upper():
        return _first_match([r"PAN\s*[:\-]\s*([A-Z0-9]+)"], text)
    if "MSME" in document_type.upper():
        return _first_match(
            [r"Udyam Registration Number\s*[:\-]\s*([A-Z0-9\-]+)"],
            text,
        )
    return _first_match(
        [
            r"Registration Number\s*[:\-]\s*([A-Z0-9\-\/]+)",
            r"Certificate No\s*[:\-]\s*([A-Z0-9\-\/]+)",
            r"Contract No\s*[:\-]\s*([A-Z0-9\-\/]+)",
        ],
        text,
    )


def _extract_date(text: str) -> str | None:
    return _first_match(
        [
            r"Date of Registration\s*[:\-]\s*(.+?)(?=\s+(?:Status|Category|Major Activity|Type of Taxpayer)\s*:|$)",
            r"Date of Incorporation\s*[:\-]\s*(.+?)(?=\s+(?:Father's Name|Address)\s*:|$)",
            r"Dated\s*[:\-]?\s*(.+?)(?=\s+(?:TO WHOMSOEVER|Contract Duration|Contract No)\s|$)",
            r"Validity(?: Date)?\s*[:\-]\s*(.+?)(?=\s+[A-Z][A-Za-z ]+\s*:|$)",
            r"Expiry(?: Date)?\s*[:\-]\s*(.+?)(?=\s+[A-Z][A-Za-z ]+\s*:|$)",
        ],
        text,
    )


def _extract_key_fields(text: str, document_type: str) -> dict:
    key_fields: dict[str, str | float | int] = {}
    gstin = _first_match([r"GSTIN\s*[:\-]\s*([A-Z0-9]+)"], text)
    pan = _first_match([r"\bPAN\s*[:\-]\s*([A-Z0-9]+)"], text)
    udyam = _first_match(
        [r"Udyam Registration Number\s*[:\-]\s*([A-Z0-9\-]+)"],
        text,
    )
    status = _first_match([r"Status\s*[:\-]\s*(.+?)(?=\s+(?:Type of Taxpayer)\s*:|$)"], text)
    category = _first_match([r"Category\s*[:\-]\s*(.+?)(?=\s+(?:Major Activity)\s*:|$)"], text)
    contract_value = _parse_indian_amount(
        _first_match([r"Total Contract Value\s*[:\-]\s*Rs\.?\s*([\d,]+)"], text)
    )
    turnover_lakhs = _parse_indian_amount(
        _first_match(
            [
                r"Annual Turnover\s*[:\-]\s*Rs\.?\s*([\d,]+)\s*Lakhs?",
                r"Turnover\s*[:\-]\s*Rs\.?\s*([\d,]+)\s*Lakhs?",
            ],
            text,
        )
    )
    emd_amount = _parse_indian_amount(
        _first_match(
            [
                r"Earnest Money Deposit\s*[:\-]\s*Rs\.?\s*([\d,]+)",
                r"\bEMD\b\s*[:\-]\s*Rs\.?\s*([\d,]+)",
            ],
            text,
        )
    )
    experience_years_match = _first_match(
        [r"(\d+)\s+years", r"period of\s+([A-Z0-9 ]+)\s+years"],
        text,
    )

    if gstin:
        key_fields["gstin"] = gstin
    if pan:
        key_fields["pan"] = pan
    if udyam:
        key_fields["udyam_registration_number"] = udyam
    if status:
        key_fields["status"] = status
    if category:
        key_fields["category"] = category
    if contract_value is not None:
        key_fields["contract_value"] = contract_value
    if turnover_lakhs is not None:
        key_fields["annual_turnover_lakhs"] = turnover_lakhs
    if emd_amount is not None:
        key_fields["emd_amount"] = emd_amount
    if experience_years_match:
        digits = re.search(r"\d+", experience_years_match)
        if digits:
            key_fields["experience_years"] = int(digits.group())

    if "Experience Certificate" in document_type:
        contract_number = _first_match([r"Contract No\s*[:\-]\s*([A-Z0-9\/\-]+)"], text)
        if contract_number:
            key_fields["contract_number"] = contract_number

    return key_fields


def _build_text_result(text: str, doc_type: str, filename: str | None, mime_type: str | None) -> dict:
    line_text = _normalize_text(text)
    normalized_excerpt = re.sub(r"\s+", " ", line_text)
    document_type = _infer_document_type(line_text, doc_type, filename)
    key_fields = _extract_key_fields(line_text, document_type)
    confidence_score = 0.97 if normalized_excerpt else 0.0

    result = {
        "document_type": document_type,
        "entity_name": _extract_entity_name(line_text),
        "registration_number": _extract_registration_number(line_text, document_type),
        "address": _extract_address(line_text),
        "validity_date": _extract_date(line_text),
        "key_fields": key_fields,
        "confidence_score": confidence_score,
        "needs_human_review": confidence_score < 0.85,
        "source_text_excerpt": normalized_excerpt[:1200],
        "source_filename": filename,
        "mime_type": mime_type,
        "doc_type_input": doc_type,
    }

    for derived_key in ("annual_turnover_lakhs", "emd_amount", "experience_years"):
        if derived_key in key_fields:
            result[derived_key] = key_fields[derived_key]

    return result


def _build_fallback_image_result(doc_type: str, filename: str | None, mime_type: str | None) -> dict:
    return {
        "document_type": _infer_document_type("", doc_type, filename),
        "entity_name": None,
        "registration_number": None,
        "address": None,
        "validity_date": None,
        "key_fields": {},
        "confidence_score": 0.0,
        "needs_human_review": True,
        "source_text_excerpt": "",
        "source_filename": filename,
        "mime_type": mime_type,
        "doc_type_input": doc_type,
        "error": "Document could not be read automatically. Human review required.",
    }


def extract_document_data(
    document_bytes: bytes,
    doc_type: str = "certificate",
    mime_type: str | None = None,
    filename: str | None = None,
) -> dict:
    """
    Extracts key fields from uploaded bidder documents.
    PDF documents use deterministic text parsing; images use Gemini Vision with
    a safe fallback when the model is unavailable.
    """
    lower_name = (filename or "").lower()
    is_pdf = (mime_type or "").lower() == "application/pdf" or lower_name.endswith(".pdf")

    if is_pdf:
        pdf_text = _extract_pdf_text(document_bytes)
        return _build_text_result(pdf_text, doc_type, filename, mime_type)

    enhanced = enhance_image(document_bytes)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return _build_fallback_image_result(doc_type, filename, mime_type)

    b64_image = base64.b64encode(enhanced).decode("utf-8")
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
You are analyzing a scanned government document of type: {doc_type}.

Extract all visible key information and return ONLY a JSON object:
{{
  "document_type": "detected type of document",
  "entity_name": "name of company or person",
  "registration_number": "any ID/registration number found",
  "address": "full address if visible",
  "validity_date": "expiry or issue date if found",
  "source_text_excerpt": "short verbatim excerpt from the visible text",
  "key_fields": {{
    "field_name": "value"
  }},
  "confidence_score": 0.0 to 1.0,
  "needs_human_review": true or false
}}

Return ONLY valid JSON. No markdown.
"""

    try:
        response = model.generate_content(
            [
                {"mime_type": "image/png", "data": b64_image},
                prompt,
            ]
        )
        result = json.loads(_clean_model_json(response.text))
        result["source_filename"] = filename
        result["mime_type"] = mime_type
        result["doc_type_input"] = doc_type
        if not result.get("source_text_excerpt"):
            result["source_text_excerpt"] = " ".join(
                str(value)
                for value in [
                    result.get("document_type"),
                    result.get("entity_name"),
                    result.get("registration_number"),
                    result.get("address"),
                    result.get("validity_date"),
                ]
                if value
            )[:1200]
        if result.get("confidence_score", 1.0) < 0.85:
            result["needs_human_review"] = True
        return result
    except Exception:
        return _build_fallback_image_result(doc_type, filename, mime_type)
