from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import PyPDF2, io, json, datetime

from agents.tender_analyst import analyze_tender
from agents.vision_specialist import extract_document_data
from agents.consistency_auditor import audit_consistency
from agents.verdict_generator import generate_verdict

app = FastAPI(title="Bharat-Procure AI", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# In-memory store (fine for hackathon demo)
# ─────────────────────────────────────────
audit_log = []  # stores every evaluation with timestamp


def log_entry(action: str, result: dict):
    """Saves every AI decision to audit log."""
    audit_log.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "model": "gemini-1.5-flash",
        "result_summary": str(result)[:200]  # first 200 chars
    })


# ─────────────────────────────────────────
# EXISTING ENDPOINTS (from Day 1)
# ─────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Bharat-Procure AI v2.0 is running ✅"}


@app.post("/analyze-tender")
async def analyze_tender_endpoint(file: UploadFile = File(...)):
    """Upload tender PDF → get structured checklist."""
    content = await file.read()
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        return {"error": f"Could not read PDF: {str(e)}"}

    if not text.strip():
        return {"error": "PDF appears scanned/empty."}

    result = analyze_tender(text)
    log_entry("analyze_tender", result)
    return {"status": "success", "checklist": result}


@app.post("/analyze-document")
async def analyze_document_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form(default="certificate")
):
    """Upload bidder document image → get extracted fields."""
    content = await file.read()
    result = extract_document_data(content, doc_type)
    log_entry("analyze_document", result)
    return {
        "status": "success",
        "data": result,
        "alert": "⚠️ Human review required!" if result.get("needs_human_review") else None
    }


# ─────────────────────────────────────────
# NEW DAY 2 ENDPOINTS
# ─────────────────────────────────────────

@app.post("/audit-consistency")
async def audit_consistency_endpoint(documents: list):
    """
    Pass a list of extracted document dicts.
    Returns cross-document consistency report.
    """
    if not documents:
        return {"error": "No documents provided"}

    result = audit_consistency(documents)
    log_entry("audit_consistency", result)
    return {"status": "success", "audit": result}


@app.post("/generate-verdict")
async def generate_verdict_endpoint(payload: dict):
    """
    Pass tender_checklist + bidder_documents + audit_report.
    Returns final PASS/FAIL verdict.
    
    Expected payload:
    {
        "tender_checklist": {...},
        "bidder_documents": [...],
        "audit_report": {...}
    }
    """
    checklist = payload.get("tender_checklist")
    documents = payload.get("bidder_documents")
    audit = payload.get("audit_report")

    if not all([checklist, documents, audit]):
        return {"error": "Missing required fields: tender_checklist, bidder_documents, audit_report"}

    result = generate_verdict(checklist, documents, audit)
    log_entry("generate_verdict", result)
    return {"status": "success", "verdict": result}


@app.post("/evaluate-full-pipeline")
async def full_pipeline(
    tender_pdf: UploadFile = File(...),
    bidder_docs: List[UploadFile] = File(...),
    doc_types: str = Form(default="certificate,certificate,certificate")
):
    """
    ⭐ THE MAIN ENDPOINT ⭐
    Upload everything at once:
    - tender_pdf: the tender document
    - bidder_docs: list of bidder document images
    - doc_types: comma separated types eg. "GST,PAN,MSME"
    
    Returns complete evaluation in one call.
    """

    # ── Step 1: Analyze tender ──
    tender_content = await tender_pdf.read()
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(tender_content))
        tender_text = ""
        for page in pdf_reader.pages:
            tender_text += page.extract_text() or ""
    except Exception as e:
        return {"error": f"Could not read tender PDF: {str(e)}"}

    tender_checklist = analyze_tender(tender_text)
    log_entry("pipeline_step1_tender", tender_checklist)

    # ── Step 2: Analyze each bidder document ──
    types_list = [t.strip() for t in doc_types.split(",")]
    extracted_docs = []

    for i, doc_file in enumerate(bidder_docs):
        doc_content = await doc_file.read()
        doc_type = types_list[i] if i < len(types_list) else "certificate"
        extracted = extract_document_data(doc_content, doc_type)
        extracted["source_filename"] = doc_file.filename
        extracted_docs.append(extracted)

    log_entry("pipeline_step2_documents", {"count": len(extracted_docs)})

    # ── Step 3: Consistency audit ──
    audit_report = audit_consistency(extracted_docs)
    log_entry("pipeline_step3_audit", audit_report)

    # ── Step 4: Generate final verdict ──
    verdict = generate_verdict(tender_checklist, extracted_docs, audit_report)
    log_entry("pipeline_step4_verdict", verdict)

    # ── Return everything ──
    return {
        "status": "success",
        "pipeline_results": {
            "tender_checklist": tender_checklist,
            "extracted_documents": extracted_docs,
            "consistency_audit": audit_report,
            "final_verdict": verdict
        },
        "audit_log_entries": len(audit_log)
    }


@app.get("/audit-log")
def get_audit_log():
    """
    Returns full audit trail — every AI decision with timestamp.
    This is what makes the system government-auditable.
    """
    return {
        "total_entries": len(audit_log),
        "log": audit_log
    }