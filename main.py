from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import PyPDF2, io

from agents.tender_analyst import analyze_tender
from agents.vision_specialist import extract_document_data

app = FastAPI(title="Bharat-Procure AI", version="1.0")

# Allow Member 3's frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "Bharat-Procure AI is running ✅"}


@app.post("/analyze-tender")
async def analyze_tender_endpoint(file: UploadFile = File(...)):
    """
    Upload a tender PDF → get back a structured checklist of requirements.
    """
    content = await file.read()

    # Extract text from PDF
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        return {"error": f"Could not read PDF: {str(e)}"}

    if not text.strip():
        return {"error": "PDF appears to be scanned/empty. Use image endpoint instead."}

    result = analyze_tender(text)
    return {"status": "success", "checklist": result}


@app.post("/analyze-document")
async def analyze_document_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form(default="certificate")
):
    """
    Upload a bidder's document (image/photo) → get extracted fields + confidence score.
    """
    content = await file.read()
    result = extract_document_data(content, doc_type)

    return {
        "status": "success",
        "data": result,
        "alert": "⚠️ Human review required!" if result.get("needs_human_review") else None
    }