import google.generativeai as genai
import cv2
import numpy as np
from PIL import Image
import os, json, base64, io
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def enhance_image(image_bytes: bytes) -> bytes:
    """
    Uses OpenCV to fix blurry/skewed photos from mobile cameras.
    Returns cleaned image bytes.
    """
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return image_bytes  # return original if OpenCV can't read it

    # Step 1: Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Step 2: Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Step 3: Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(denoised, -1, kernel)

    # Step 4: Adaptive threshold (makes text pop out clearly)
    enhanced = cv2.adaptiveThreshold(
        sharpened, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    # Convert back to bytes
    _, buffer = cv2.imencode('.png', enhanced)
    return buffer.tobytes()


def extract_document_data(image_bytes: bytes, doc_type: str = "certificate") -> dict:
    """
    Sends enhanced image to Gemini Vision to extract key fields.
    Returns structured data with a confidence score.
    """
    # First enhance the image
    enhanced = enhance_image(image_bytes)

    # Convert to base64 for Gemini
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
  "key_fields": {{
    "field_name": "value"
  }},
  "confidence_score": 0.0 to 1.0 (how clearly readable was this document),
  "needs_human_review": true or false (set true if confidence below 0.85)
}}

Return ONLY valid JSON. No markdown.
"""

    response = model.generate_content([
        {"mime_type": "image/png", "data": b64_image},
        prompt
    ])

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        result = json.loads(raw)
        # Force HITL if confidence is low
        if result.get("confidence_score", 1.0) < 0.85:
            result["needs_human_review"] = True
        return result
    except json.JSONDecodeError:
        return {
            "error": "Could not parse document",
            "raw_response": raw,
            "needs_human_review": True,
            "confidence_score": 0.0
        }