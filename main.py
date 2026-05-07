import datetime
import io
import json
import os
import re
from typing import List
from urllib.parse import quote

import PyPDF2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agents.audit_logger import (
    get_full_log,
    get_hitl_entries,
    get_log_for_bidder,
    get_log_for_tender,
    log_action,
)
from agents.consistency_auditor import audit_consistency
from agents.rule_engine import (
    check_financial_requirements,
    check_statutory_documents,
)
from agents.tender_analyst import analyze_tender
from agents.verdict_generator import generate_verdict
from agents.vision_specialist import extract_document_data

app = FastAPI(title="Bharat-Procure AI", version="3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OFFICER_PROFILE_FILE = os.path.join(BASE_DIR, "officer_profile.json")
EVALUATION_HISTORY_FILE = os.path.join(BASE_DIR, "evaluation_history.json")
LATEST_PIPELINE_FILE = os.path.join(BASE_DIR, "latest_pipeline_result.json")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploaded_documents")
FRONTEND_FILES = {
    "dashboard_v1.html",
    "upload_tender.html",
    "all_bidders.html",
    "active_evals.html",
    "analytics.html",
    "audit_trail.html",
    "settings.html",
    "help.html",
    "dashboard_app.js",
    "dashboard_theme.css",
}

audit_log = []
LATEST_PIPELINE_RESULT = None


def _safe_filename(filename: str | None, fallback: str) -> str:
    raw_name = os.path.basename(filename or fallback).strip()
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_name)
    safe_name = re.sub(r"\s+", "_", safe_name).strip("._ ")
    return safe_name[:120] or fallback


def _safe_storage_id(value: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", value or "UNKNOWN").strip("_")
    return cleaned[:60] or "UNKNOWN"


def _save_uploaded_file(run_id: str, filename: str | None, content: bytes, prefix: str) -> dict:
    os.makedirs(os.path.join(UPLOADS_DIR, run_id), exist_ok=True)
    safe_name = _safe_filename(filename, f"{prefix}.bin")
    stored_name = _safe_filename(f"{prefix}_{safe_name}", f"{prefix}.bin")
    stored_path = os.path.join(UPLOADS_DIR, run_id, stored_name)
    with open(stored_path, "wb") as handle:
        handle.write(content)
    return {
        "original_filename": filename or safe_name,
        "stored_filename": stored_name,
        "saved_path": stored_path,
        "saved_url": f"/uploads/{quote(run_id)}/{quote(stored_name)}",
        "size_bytes": len(content),
    }


def _is_valid_bidder_name(value: str | None) -> bool:
    if not value:
        return False
    cleaned = value.strip(" :;-_")
    lowered = cleaned.lower()
    invalid_values = {"unknown", "date of birth", "dob", "name", "address", "status", "type"}
    invalid_phrases = (
        "date of birth",
        "standard bidding document",
        "procurement of civil works",
        "instructions to bidders",
        "government of india",
    )
    return bool(
        cleaned
        and lowered not in invalid_values
        and not any(phrase in lowered for phrase in invalid_phrases)
        and re.search(r"[A-Za-z0-9]", cleaned)
    )


def _bidder_label_from_filename(filename: str | None) -> str:
    safe_name = _safe_filename(filename, "document.pdf")
    label = os.path.splitext(safe_name)[0]
    label = re.sub(r"^(?:bidder|document|doc|file)[_-]*\d*[_-]*", "", label, flags=re.IGNORECASE)
    label = re.sub(r"[_-]+", " ", label).strip()
    if not label:
        return f"Unidentified bidder ({safe_name})"
    return label.title()


def _fallback_bidder_name(extracted_docs: list[dict]) -> str:
    for document in extracted_docs:
        filename = document.get("source_filename") or document.get("saved_file", {}).get("original_filename")
        if filename:
            return _bidder_label_from_filename(filename)
    return "Unidentified bidder"


def _display_bidder_name_from_record(record: dict) -> str:
    if _is_valid_bidder_name(record.get("bidder_name")):
        return record["bidder_name"].strip(" :;-_")

    saved_documents = record.get("saved_documents") or []
    if saved_documents:
        filename = saved_documents[0].get("original_filename") or saved_documents[0].get("stored_filename")
        return _bidder_label_from_filename(filename)

    extracted_documents = record.get("extracted_documents") or []
    if extracted_documents:
        return _fallback_bidder_name(extracted_documents)

    return "Unidentified bidder"


def _normalize_evaluation_record(record: dict) -> dict:
    normalized = {**record}
    display_name = _display_bidder_name_from_record(normalized)
    normalized["bidder_name"] = display_name
    if normalized.get("summary"):
        normalized["summary"] = re.sub(
            r"^(?:UNKNOWN|Date of birth:|Bidder)\s+scored",
            f"{display_name} scored",
            normalized["summary"],
            flags=re.IGNORECASE,
        )
    return normalized


def _read_json_file(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return default if payload is None else payload
    except Exception:
        return default


def _write_json_file(path: str, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _title_case_username(raw_username: str) -> str:
    cleaned = re.sub(r"[_\-.]+", " ", raw_username).strip()
    if not cleaned:
        return "Officer"
    return " ".join(part.capitalize() for part in cleaned.split())


def _default_officer_profile() -> dict:
    username = os.getenv("USERNAME") or os.getenv("USER") or "Officer"
    display_name = _title_case_username(username)
    officer_id = os.getenv("OFFICER_ID") or f"USR-{re.sub(r'[^A-Z0-9]', '', username.upper())[:12] or 'OFFICER'}"
    return {
        "officer_id": officer_id,
        "name": display_name,
        "role": os.getenv("OFFICER_ROLE", "Procurement Review Officer"),
        "department": os.getenv("OFFICER_DEPARTMENT") or os.getenv("COMPUTERNAME") or "Local Review Cell",
        "clearance_level": os.getenv("OFFICER_CLEARANCE", "L1"),
        "source": "environment",
        "last_updated": datetime.datetime.now().isoformat(),
    }


def get_officer_profile_data() -> dict:
    profile = _read_json_file(OFFICER_PROFILE_FILE, {})
    default_profile = _default_officer_profile()
    merged = {**default_profile, **profile}
    if merged != profile:
        _write_json_file(OFFICER_PROFILE_FILE, merged)
    return merged


def save_officer_profile_data(payload: dict) -> dict:
    current = get_officer_profile_data()
    updated = {
        **current,
        "officer_id": payload.get("officer_id", current["officer_id"]).strip() or current["officer_id"],
        "name": payload.get("name", current["name"]).strip() or current["name"],
        "role": payload.get("role", current["role"]).strip() or current["role"],
        "department": payload.get("department", current["department"]).strip() or current["department"],
        "clearance_level": payload.get("clearance_level", current["clearance_level"]).strip() or current["clearance_level"],
        "source": "settings",
        "last_updated": datetime.datetime.now().isoformat(),
    }
    _write_json_file(OFFICER_PROFILE_FILE, updated)
    return updated


def _load_evaluation_history() -> list:
    return _read_json_file(EVALUATION_HISTORY_FILE, [])


def _save_evaluation_history(history: list):
    _write_json_file(EVALUATION_HISTORY_FILE, history)


def _build_evaluation_summary(pipeline_results: dict) -> dict:
    verdict = pipeline_results.get("final_verdict", {})
    documents = pipeline_results.get("extracted_documents", [])
    review_items = verdict.get("human_review_items", [])
    return {
        "evaluation_id": f"EVAL-{len(_load_evaluation_history()) + 1:04d}",
        "generated_at": pipeline_results.get("generated_at"),
        "tender_id": pipeline_results.get("tender_id"),
        "bidder_name": pipeline_results.get("bidder_name"),
        "verdict": verdict.get("bidder_verdict"),
        "bid_amount": pipeline_results.get("bid_amount"),
        "score_percent": verdict.get("score_percent"),
        "summary": verdict.get("summary"),
        "open_review_count": len(review_items),
        "open_review_items": review_items,
        "missing_documents": pipeline_results.get("statutory_rules", {}).get("missing_documents", []),
        "document_count": len(documents),
        "document_types": [document.get("document_type") for document in documents if document.get("document_type")],
        "upload_run_id": pipeline_results.get("upload_run_id"),
        "saved_tender": pipeline_results.get("saved_tender"),
        "saved_documents": [document.get("saved_file") for document in documents if document.get("saved_file")],
        "latest_extracted_text": next(
            (document.get("source_text_excerpt") for document in documents if document.get("source_text_excerpt")),
            "",
        ),
    }


def _append_evaluation_history(pipeline_results: dict):
    history = [_normalize_evaluation_record(record) for record in _load_evaluation_history()]
    summary = _build_evaluation_summary(pipeline_results)
    history.append(summary)
    _save_evaluation_history(history[-50:])


def _normalize_manual_verdict(verdict: str | None) -> str:
    normalized = re.sub(r"\s+", "_", (verdict or "REFER_TO_COMMITTEE").strip().upper())
    if normalized == "REVIEW":
        return "REFER_TO_COMMITTEE"
    return normalized if normalized in {"PASS", "FAIL", "REFER_TO_COMMITTEE"} else "REFER_TO_COMMITTEE"


def _build_manual_bidder_summary(bidder_name: str, tender_id: str, bid_amount: str) -> str:
    amount_text = f" Bid amount: Rs. {bid_amount}." if bid_amount else " Bid amount not recorded."
    return f"Manual bidder record for {bidder_name} under tender {tender_id}.{amount_text}"


def log_entry(action: str, result: dict, model_version: str = "gemini-1.5-flash"):
    audit_log.append(
        {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action,
            "model": model_version,
            "result_summary": str(result)[:200],
        }
    )


def _read_pdf_text(content: bytes) -> str:
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
    pages = []
    for page in pdf_reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _extract_tender_id(text: str, checklist: dict | None = None) -> str:
    if checklist and checklist.get("tender_id"):
        return checklist["tender_id"]
    match = re.search(
        r"(?:TENDER\s*(?:NO|NUMBER)|REFERENCE\s*(?:NO|NUMBER))\s*[:\-]\s*([A-Z0-9\/\-]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else "UNKNOWN"


def _build_bidder_profile(extracted_docs: list[dict]) -> dict:
    profile = {
        "entity_name": None,
        "annual_turnover_lakhs": None,
        "emd_amount": None,
        "experience_years": None,
        "document_types": [],
        "submitted_document_count": len(extracted_docs),
    }
    for document in extracted_docs:
        key_fields = document.get("key_fields", {}) or {}
        if not profile["entity_name"] and _is_valid_bidder_name(document.get("entity_name")):
            profile["entity_name"] = document["entity_name"].strip(" :;-_")
        for field_name in ("annual_turnover_lakhs", "emd_amount", "experience_years"):
            value = document.get(field_name, key_fields.get(field_name))
            if value is not None and profile[field_name] is None:
                profile[field_name] = value
        if document.get("document_type"):
            profile["document_types"].append(document["document_type"])
    return profile


def _parse_timestamp(raw_timestamp: str | None) -> datetime.datetime | None:
    if not raw_timestamp:
        return None
    try:
        return datetime.datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return None


def _build_dashboard_metrics() -> dict:
    entries = get_full_log()
    history = _load_evaluation_history()
    today = datetime.date.today()
    unique_tenders = {
        entry.get("tender_id")
        for entry in entries
        if entry.get("tender_id") and entry.get("tender_id") != "UNKNOWN"
    }
    unique_bidders_today = set()
    for record in history:
        record_time = _parse_timestamp(record.get("generated_at"))
        bidder_name = _display_bidder_name_from_record(record)
        if record_time and record_time.date() == today and bidder_name:
            unique_bidders_today.add(bidder_name)

    latest_score = None
    pending_review = len(get_hitl_entries())
    if LATEST_PIPELINE_RESULT:
        verdict = LATEST_PIPELINE_RESULT["pipeline_results"].get("final_verdict", {})
        latest_score = verdict.get("score_percent")
        pending_review = len(verdict.get("human_review_items", []))

    return {
        "active_tenders": len(unique_tenders) or len({record.get("tender_id") for record in history if record.get("tender_id")}),
        "bidders_evaluated_today": len(unique_bidders_today),
        "hitl_pending": pending_review,
        "latest_score_percent": latest_score,
        "audit_entries": len(entries),
    }


def _persist_pipeline_state(pipeline_results: dict):
    global LATEST_PIPELINE_RESULT
    LATEST_PIPELINE_RESULT = {
        "generated_at": datetime.datetime.now().isoformat(),
        "pipeline_results": pipeline_results,
    }
    _write_json_file(LATEST_PIPELINE_FILE, LATEST_PIPELINE_RESULT)


LATEST_PIPELINE_RESULT = _read_json_file(LATEST_PIPELINE_FILE, None)


@app.get("/")
def root():
    return {
        "status": "Bharat-Procure AI v3.2 is running",
        "dashboard_url": "/ui/dashboard_v1.html",
        "upload_url": "/ui/upload_tender.html",
    }


@app.get("/ui/{filename}", include_in_schema=False)
def serve_frontend_file(filename: str):
    if filename not in FRONTEND_FILES:
        raise HTTPException(status_code=404, detail="Frontend file not found")
    return FileResponse(os.path.join(BASE_DIR, filename))


@app.get("/uploads/{run_id}/{filename}", include_in_schema=False)
def serve_uploaded_file(run_id: str, filename: str):
    safe_run_id = _safe_storage_id(run_id)
    safe_filename = _safe_filename(filename, "document.bin")
    if safe_run_id != run_id or safe_filename != filename:
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    upload_path = os.path.abspath(os.path.join(UPLOADS_DIR, safe_run_id, safe_filename))
    upload_root = os.path.abspath(UPLOADS_DIR)
    if not upload_path.startswith(upload_root + os.sep) or not os.path.exists(upload_path):
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    return FileResponse(upload_path, filename=safe_filename)


@app.get("/officer-profile")
def get_officer_profile():
    return {"status": "success", "profile": get_officer_profile_data()}


@app.post("/officer-profile")
async def update_officer_profile(payload: dict):
    profile = save_officer_profile_data(payload)
    return {"status": "success", "profile": profile}


@app.get("/evaluations")
def get_evaluations():
    history = list(reversed([_normalize_evaluation_record(record) for record in _load_evaluation_history()]))
    latest_evaluation = None
    if LATEST_PIPELINE_RESULT:
        latest_evaluation = {
            **LATEST_PIPELINE_RESULT,
            "pipeline_results": _normalize_evaluation_record(LATEST_PIPELINE_RESULT.get("pipeline_results", {})),
        }
    return {
        "status": "success",
        "total_evaluations": len(history),
        "evaluations": history,
        "latest_evaluation": latest_evaluation,
    }


@app.post("/manual-bidders")
async def add_manual_bidder(
    bidder_name: str = Form(...),
    tender_id: str = Form(...),
    verdict: str = Form(default="REFER_TO_COMMITTEE"),
    bid_amount: str = Form(default=""),
    documents: List[UploadFile] | None = File(default=None),
):
    bidder_name = bidder_name.strip()
    tender_id = tender_id.strip()
    bid_amount = bid_amount.strip()
    normalized_verdict = _normalize_manual_verdict(verdict)

    if not bidder_name:
        raise HTTPException(status_code=400, detail="Bidder name is required")
    if not tender_id:
        raise HTTPException(status_code=400, detail="Tender name or ID is required")

    upload_run_id = f"manual_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{_safe_storage_id(tender_id)}"
    saved_documents = []
    for index, document in enumerate(documents or []):
        content = await document.read()
        if not content:
            continue
        saved_documents.append(
            _save_uploaded_file(
                upload_run_id,
                document.filename,
                content,
                f"manual_{index + 1:02d}",
            )
        )

    review_items = ["Manual review requested"] if normalized_verdict == "REFER_TO_COMMITTEE" else []
    history = [_normalize_evaluation_record(record) for record in _load_evaluation_history()]
    record = {
        "evaluation_id": f"BID-{len(history) + 1:04d}",
        "source": "manual_bidder_entry",
        "generated_at": datetime.datetime.now().isoformat(),
        "tender_id": tender_id,
        "bidder_name": bidder_name,
        "verdict": normalized_verdict,
        "bid_amount": bid_amount,
        "score_percent": None,
        "summary": _build_manual_bidder_summary(bidder_name, tender_id, bid_amount),
        "open_review_count": len(review_items),
        "open_review_items": review_items,
        "missing_documents": [],
        "document_count": len(saved_documents),
        "document_types": ["Manual Upload"] if saved_documents else [],
        "upload_run_id": upload_run_id,
        "saved_documents": saved_documents,
        "latest_extracted_text": "",
    }
    history.append(record)
    _save_evaluation_history(history[-50:])

    log_action(
        action="manual_bidder_added",
        agent="OfficerDashboard",
        input_summary=f"{bidder_name} | Tender: {tender_id}",
        result_summary=f"{normalized_verdict} | Amount: {bid_amount or 'Not recorded'}",
        model_version="human-officer",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )

    return {
        "status": "success",
        "record": _normalize_evaluation_record(record),
        "dashboard_metrics": _build_dashboard_metrics(),
    }


@app.post("/analyze-tender")
async def analyze_tender_endpoint(file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = _read_pdf_text(content)
    except Exception as exc:
        return {"error": f"Could not read PDF: {exc}"}
    if not text.strip():
        return {"error": "PDF appears scanned or empty."}

    result = analyze_tender(text)
    tender_id = _extract_tender_id(text, result)
    log_entry("analyze_tender", result)
    log_action(
        action="tender_analyzed",
        agent="TenderAnalyst",
        input_summary=file.filename or "Tender upload",
        result_summary=result.get("tender_title", "Tender analyzed"),
        model_version="gemini-1.5-flash/fallback",
        tender_id=tender_id,
    )
    return {"status": "success", "checklist": result}


@app.post("/analyze-document")
async def analyze_document_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form(default="certificate"),
):
    content = await file.read()
    result = extract_document_data(
        content,
        doc_type,
        mime_type=file.content_type,
        filename=file.filename,
    )
    log_entry("analyze_document", result)
    log_action(
        action="document_extracted",
        agent="VisionSpecialist",
        input_summary=f"{file.filename} ({doc_type})",
        result_summary=result.get("document_type", "Document analyzed"),
        confidence=result.get("confidence_score"),
        model_version="gemini-1.5-flash/fallback",
        bidder_name=result.get("entity_name"),
    )
    return {
        "status": "success",
        "data": result,
        "alert": "Human review required." if result.get("needs_human_review") else None,
    }


@app.post("/audit-consistency")
async def audit_consistency_endpoint(documents: list):
    if not documents:
        return {"error": "No documents provided"}
    result = audit_consistency(documents)
    bidder_name = next((doc.get("entity_name") for doc in documents if doc.get("entity_name")), "UNKNOWN")
    log_entry("audit_consistency", result, model_version="deterministic-python")
    log_action(
        action="consistency_checked",
        agent="ConsistencyAuditor",
        input_summary=f"Documents compared: {len(documents)}",
        result_summary=result.get("overall_status", "UNKNOWN"),
        model_version="deterministic-python",
        bidder_name=bidder_name,
    )
    return {"status": "success", "audit": result}


@app.post("/generate-verdict")
async def generate_verdict_endpoint(payload: dict):
    checklist = payload.get("tender_checklist")
    documents = payload.get("bidder_documents")
    audit = payload.get("audit_report")
    if not all([checklist, documents, audit]):
        return {"error": "Missing required fields: tender_checklist, bidder_documents, audit_report"}

    result = generate_verdict(checklist, documents, audit)
    bidder_name = payload.get("bidder_name") or next(
        (doc.get("entity_name") for doc in documents if doc.get("entity_name")),
        "UNKNOWN",
    )
    tender_id = payload.get("tender_id") or checklist.get("tender_id", "UNKNOWN")
    log_entry("generate_verdict", result)
    log_action(
        action="verdict_generated",
        agent="VerdictGenerator",
        input_summary=f"Bidder: {bidder_name}",
        result_summary=result.get("bidder_verdict", "UNKNOWN"),
        model_version="gemini-1.5-flash/fallback",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    return {"status": "success", "verdict": result}


@app.post("/evaluate-full-pipeline")
async def full_pipeline(
    tender_pdf: UploadFile = File(...),
    bidder_docs: List[UploadFile] = File(...),
    doc_types: str = Form(default="certificate,certificate,certificate"),
):
    tender_content = await tender_pdf.read()
    try:
        tender_text = _read_pdf_text(tender_content)
    except Exception as exc:
        return {"error": f"Could not read tender PDF: {exc}"}
    if not tender_text:
        return {"error": "Tender PDF appears empty."}

    tender_checklist = analyze_tender(tender_text)
    tender_id = _extract_tender_id(tender_text, tender_checklist)
    upload_run_id = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{_safe_storage_id(tender_id)}"
    saved_tender = _save_uploaded_file(
        upload_run_id,
        tender_pdf.filename,
        tender_content,
        "tender",
    )
    log_entry("pipeline_step_tender", tender_checklist)
    log_action(
        action="tender_analyzed",
        agent="TenderAnalyst",
        input_summary=tender_pdf.filename or "Tender upload",
        result_summary=tender_checklist.get("tender_title", "Tender analyzed"),
        model_version="gemini-1.5-flash/fallback",
        tender_id=tender_id,
    )

    types_list = [item.strip() for item in doc_types.split(",") if item.strip()]
    extracted_docs = []
    for index, doc_file in enumerate(bidder_docs):
        doc_content = await doc_file.read()
        doc_type = types_list[index] if index < len(types_list) else "certificate"
        saved_file = _save_uploaded_file(
            upload_run_id,
            doc_file.filename,
            doc_content,
            f"bidder_{index + 1:02d}",
        )
        extracted = extract_document_data(
            doc_content,
            doc_type,
            mime_type=doc_file.content_type,
            filename=doc_file.filename,
        )
        extracted["saved_file"] = saved_file
        extracted["saved_url"] = saved_file["saved_url"]
        extracted["saved_size_bytes"] = saved_file["size_bytes"]
        extracted_docs.append(extracted)
        log_action(
            action="document_extracted",
            agent="VisionSpecialist",
            input_summary=f"{doc_file.filename} ({doc_type})",
            result_summary=extracted.get("document_type", "Document analyzed"),
            confidence=extracted.get("confidence_score"),
            model_version="gemini-1.5-flash/fallback",
            tender_id=tender_id,
            bidder_name=extracted.get("entity_name"),
    )

    bidder_profile = _build_bidder_profile(extracted_docs)
    bidder_name = bidder_profile.get("entity_name") or _fallback_bidder_name(extracted_docs)
    bidder_profile["entity_name"] = bidder_name
    audit_report = audit_consistency(extracted_docs)
    financial_rules = check_financial_requirements(bidder_profile, tender_checklist)
    statutory_rules = check_statutory_documents(extracted_docs, tender_checklist)
    verdict = generate_verdict(tender_checklist, extracted_docs, audit_report)
    if verdict.get("summary", "").startswith("Bidder scored"):
        verdict["summary"] = verdict["summary"].replace("Bidder scored", f"{bidder_name} scored", 1)
    verdict.setdefault("supporting_checks", {})
    verdict["supporting_checks"]["financial_rules"] = financial_rules
    verdict["supporting_checks"]["statutory_rules"] = statutory_rules

    log_entry("pipeline_step_documents", {"count": len(extracted_docs)}, model_version="mixed")
    log_entry("pipeline_step_audit", audit_report, model_version="deterministic-python")
    log_entry("pipeline_step_verdict", verdict)

    log_action(
        action="consistency_checked",
        agent="ConsistencyAuditor",
        input_summary=f"Documents compared: {len(extracted_docs)}",
        result_summary=audit_report.get("overall_status", "UNKNOWN"),
        model_version="deterministic-python",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    log_action(
        action="financial_rules_checked",
        agent="RuleEngine",
        input_summary=f"Bidder: {bidder_name}",
        result_summary=financial_rules["financial_check_summary"]["overall"],
        model_version="deterministic-python",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    log_action(
        action="statutory_docs_checked",
        agent="RuleEngine",
        input_summary=f"Bidder: {bidder_name} | Docs: {len(extracted_docs)}",
        result_summary=statutory_rules["statutory_check_summary"]["overall"],
        model_version="deterministic-python",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    log_action(
        action="verdict_generated",
        agent="VerdictGenerator",
        input_summary=f"Bidder: {bidder_name}",
        result_summary=verdict.get("bidder_verdict", "UNKNOWN"),
        model_version="gemini-1.5-flash/fallback",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )

    pipeline_results = {
        "upload_run_id": upload_run_id,
        "saved_tender": saved_tender,
        "tender_id": tender_id,
        "bidder_name": bidder_name,
        "bidder_profile": bidder_profile,
        "tender_checklist": tender_checklist,
        "extracted_documents": extracted_docs,
        "consistency_audit": audit_report,
        "financial_rules": financial_rules,
        "statutory_rules": statutory_rules,
        "final_verdict": verdict,
        "generated_at": datetime.datetime.now().isoformat(),
    }
    _persist_pipeline_state(pipeline_results)
    _append_evaluation_history(pipeline_results)

    return {
        "status": "success",
        "pipeline_results": pipeline_results,
        "dashboard_metrics": _build_dashboard_metrics(),
        "audit_log_entries": len(audit_log),
    }


@app.get("/audit-log")
def get_audit_log():
    return {
        "total_entries": len(audit_log),
        "log": audit_log,
    }


@app.post("/test-blurry-image")
async def test_blurry_image(file: UploadFile = File(...)):
    content = await file.read()
    import cv2
    import numpy as np

    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is not None:
        blurred = cv2.GaussianBlur(img, (15, 15), 0)
        _, buffer = cv2.imencode(".png", blurred)
        test_content = buffer.tobytes()
    else:
        test_content = content

    result = extract_document_data(
        test_content,
        "stress_test",
        mime_type=file.content_type,
        filename=file.filename,
    )
    return {
        "status": "success",
        "stress_test": True,
        "image_was_blurred": img is not None,
        "system_handled_gracefully": True,
        "result": result,
        "hitl_triggered": result.get("needs_human_review", False),
    }


@app.get("/system-health")
def system_health():
    key = os.getenv("GEMINI_API_KEY")
    audit_entries = get_full_log()
    return {
        "status": "healthy",
        "version": "3.2",
        "gemini_key_configured": bool(key and len(key) > 10),
        "agents_loaded": [
            "tender_analyst",
            "vision_specialist",
            "consistency_auditor",
            "verdict_generator",
            "rule_engine",
            "audit_logger",
        ],
        "total_audit_log_entries": len(audit_entries),
        "endpoints": 20,
    }


@app.get("/dashboard-state")
def dashboard_state():
    history = list(reversed([_normalize_evaluation_record(record) for record in _load_evaluation_history()]))
    latest_evaluation = None
    if LATEST_PIPELINE_RESULT:
        latest_evaluation = {
            **LATEST_PIPELINE_RESULT,
            "pipeline_results": _normalize_evaluation_record(LATEST_PIPELINE_RESULT.get("pipeline_results", {})),
        }
    return {
        "status": "success",
        "metrics": _build_dashboard_metrics(),
        "latest_evaluation": latest_evaluation,
        "recent_audit": list(reversed(get_full_log()[-20:])),
        "officer_profile": get_officer_profile_data(),
        "evaluation_history": history,
        "system_health": system_health(),
    }


@app.post("/check-financial-rules")
async def check_financial_rules(payload: dict):
    bidder_data = payload.get("bidder_data", {})
    tender_checklist = payload.get("tender_checklist", {})
    bidder_name = payload.get("bidder_name") or bidder_data.get("entity_name") or "Unknown"
    tender_id = payload.get("tender_id") or tender_checklist.get("tender_id", "Unknown")

    result = check_financial_requirements(bidder_data, tender_checklist)
    log_action(
        action="financial_rules_checked",
        agent="RuleEngine",
        input_summary=f"Bidder: {bidder_name}",
        result_summary=result["financial_check_summary"]["overall"],
        model_version="deterministic-python",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    return {"status": "success", "result": result}


@app.post("/check-statutory-documents")
async def check_statutory_docs(payload: dict):
    extracted_docs = payload.get("extracted_docs", [])
    tender_checklist = payload.get("tender_checklist", {})
    bidder_name = payload.get("bidder_name", "Unknown")
    tender_id = payload.get("tender_id") or tender_checklist.get("tender_id", "Unknown")

    result = check_statutory_documents(extracted_docs, tender_checklist)
    log_action(
        action="statutory_docs_checked",
        agent="RuleEngine",
        input_summary=f"Bidder: {bidder_name} | Docs: {len(extracted_docs)}",
        result_summary=result["statutory_check_summary"]["overall"],
        model_version="deterministic-python",
        tender_id=tender_id,
        bidder_name=bidder_name,
    )
    return {"status": "success", "result": result}


@app.get("/audit-trail")
def get_audit_trail():
    entries = get_full_log()
    return {
        "status": "success",
        "total_entries": len(entries),
        "entries": entries,
    }


@app.get("/audit-trail/tender/{tender_id}")
def get_audit_by_tender(tender_id: str):
    entries = get_log_for_tender(tender_id)
    return {
        "tender_id": tender_id,
        "total_entries": len(entries),
        "entries": entries,
    }


@app.get("/audit-trail/bidder/{bidder_name}")
def get_audit_by_bidder(bidder_name: str):
    entries = get_log_for_bidder(bidder_name)
    return {
        "bidder_name": bidder_name,
        "total_entries": len(entries),
        "entries": entries,
    }


@app.get("/audit-trail/hitl")
def get_hitl_audit():
    entries = get_hitl_entries()
    return {
        "status": "success",
        "total_hitl_entries": len(entries),
        "entries": entries,
    }


@app.post("/log-officer-action")
async def log_officer_action(payload: dict):
    profile = get_officer_profile_data()
    officer_id = payload.get("officer_id") or profile.get("officer_id")
    entry = log_action(
        action=payload.get("action", "officer_action"),
        agent="OfficerDashboard",
        input_summary=payload.get("reason", "No reason provided"),
        result_summary=f"Manual action by officer {officer_id}",
        model_version="human-officer",
        officer_id=officer_id,
        tender_id=payload.get("tender_id"),
        bidder_name=payload.get("bidder_name"),
    )
    return {"status": "success", "logged_entry": entry, "officer_profile": profile}
