# 🇮🇳 Bharat-Procure AI
### Intelligent Multimodal Evaluation System for Transparent Government Procurement

Built for **[Your Hackathon Name]** | Team: [Your Team Name]

---

## 🚀 What it does
Bharat-Procure AI automates the evaluation of government tender bids using a 
4-agent AI pipeline — reducing a 10-14 day manual process to under 30 minutes.

## 🏗️ Architecture
Tender PDF → [Tender Analyst Agent] → Master Checklist
Bidder Docs → [Vision Specialist Agent] → Structured Data
↓
[Consistency Auditor] → Cross-document flags
↓
[Verdict Generator] → PASS / FAIL + Evidence
## ⚙️ Tech Stack
- **Backend:** FastAPI (Python)
- **AI/Vision:** Google Gemini 1.5 Flash
- **Image Processing:** OpenCV
- **Frontend:** Streamlit (Member 3)

## 🔧 Setup & Run

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/bharat-procure-ai.git
cd bharat-procure-ai
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate   # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Add your API key
Create a `.env` file:
GEMINI_API_KEY=your_gemini_key_here

Get free key at: https://aistudio.google.com

### 5. Run the server
```bash
uvicorn main:app --reload
```
Visit: http://127.0.0.1:8000/docs

## 📁 Mock Data for Demo
```bash
pip install fpdf
python create_mock_data.py
```
This creates sample tender + bidder documents in `/mock_data`

## 🔗 API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health status |
| `/analyze-tender` | POST | Extract rules from tender PDF |
| `/analyze-document` | POST | Extract fields from bidder doc |
| `/audit-consistency` | POST | Cross-document verification |
| `/generate-verdict` | POST | Final PASS/FAIL verdict |
| `/evaluate-full-pipeline` | POST | ⭐ Complete evaluation in one call |
| `/audit-log` | GET | Full audit trail |
| `/system-health` | GET | System status check |

## 👥 Team
- **Member 1 (You):** AI Backend + Agents
- **Member 2:** Rule Engine + Audit Logic  
- **Member 3:** Dashboard + Demo

## 🎯 Key Features
- ✅ No silent failures — low confidence triggers human review
- ✅ Cross-document integrity checks (GST vs PAN vs MSME)
- ✅ Full audit trail for government compliance
- ✅ Inclusive — works with blurry mobile-captured photos