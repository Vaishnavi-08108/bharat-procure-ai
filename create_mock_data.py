"""
Run this once to generate mock tender and bidder data for demo purposes.
Command: python create_mock_data.py
"""

from fpdf import FPDF
import os

os.makedirs("mock_data", exist_ok=True)

# ── Mock Tender PDF ──
pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", "B", 16)
pdf.cell(0, 10, "TENDER DOCUMENT - CRPF EQUIPMENT PROCUREMENT", ln=True, align="C")
pdf.set_font("Arial", size=12)
pdf.ln(5)

tender_text = """
TENDER NO: CRPF/2024/EQUIP/001
Date of Issue: 01-Jan-2024
Last Date of Submission: 31-Jan-2024

1. ELIGIBILITY CRITERIA (MANDATORY)

1.1 Financial Requirements:
- Minimum Annual Turnover: Rs. 50 Lakhs for last 3 financial years
- Earnest Money Deposit (EMD): Rs. 1,00,000

1.2 Technical Requirements:
- Must have supplied similar equipment to any Central/State Government
- Minimum 3 years of experience in relevant field
- Must possess valid ISO 9001:2015 certification

1.3 Statutory Documents Required:
- GST Registration Certificate (mandatory)
- PAN Card of the firm (mandatory)
- MSME Registration (if applicable)
- Income Tax Returns for last 3 years
- Bank Solvency Certificate

2. SCOPE OF WORK
Supply of 500 units of protective gear as per specifications.

3. EVALUATION CRITERIA
Technical bid will be evaluated first.
Financial bid of technically qualified bidders only will be opened.
"""

for line in tender_text.strip().split("\n"):
    pdf.multi_cell(0, 8, line.strip())

pdf.output("./mock_data/mock_tender.pdf")
print("✅ Created mock_data/mock_tender.pdf")


# ── Mock Bidder Document (text-based image simulation) ──
# Create a simple GST certificate as PDF (Member 3 will display this)
pdf2 = FPDF()
pdf2.add_page()
pdf2.set_font("Arial", "B", 14)
pdf2.cell(0, 10, "GST REGISTRATION CERTIFICATE", ln=True, align="C")
pdf2.set_font("Arial", size=11)
pdf2.ln(5)

gst_text = """
GSTIN: 29ABCDE1234F1Z5
Legal Name: ABC Technologies Pvt Ltd
Trade Name: ABC Tech
Address: 123, MG Road, Bengaluru, Karnataka - 560001
Date of Registration: 15-03-2019
Status: Active
Type of Taxpayer: Regular

This certificate is issued under the Goods and Services Tax Act, 2017.
"""
for line in gst_text.strip().split("\n"):
    pdf2.multi_cell(0, 8, line.strip())
pdf2.output("mock_data/mock_gst_certificate.pdf")
print("✅ Created mock_data/mock_gst_certificate.pdf")


# ── Mock PAN Card ──
pdf3 = FPDF()
pdf3.add_page()
pdf3.set_font("Arial", "B", 14)
pdf3.cell(0, 10, "PERMANENT ACCOUNT NUMBER CARD", ln=True, align="C")
pdf3.set_font("Arial", size=11)
pdf3.ln(5)

pan_text = """
PAN: ABCDE1234F
Name: ABC TECHNOLOGIES PRIVATE LIMITED
Date of Incorporation: 10-01-2018
Father's Name / Registered Address: 123, MG Road, Bengaluru, Karnataka
"""
for line in pan_text.strip().split("\n"):
    pdf3.multi_cell(0, 8, line.strip())
pdf3.output("mock_data/mock_pan_card.pdf")
print("✅ Created mock_data/mock_pan_card.pdf")


# ── Mock MSME Certificate ──
pdf4 = FPDF()
pdf4.add_page()
pdf4.set_font("Arial", "B", 14)
pdf4.cell(0, 10, "UDYAM REGISTRATION CERTIFICATE (MSME)", ln=True, align="C")
pdf4.set_font("Arial", size=11)
pdf4.ln(5)

msme_text = """
Udyam Registration Number: UDYAM-KR-01-0012345
Name of Enterprise: ABC Technologies Pvt Ltd
Type: Private Limited Company
Address: 123, MG Road, Bengaluru, Karnataka - 560001
Date of Registration: 20-04-2019
Category: Small Enterprise
Major Activity: Services
"""
for line in msme_text.strip().split("\n"):
    pdf4.multi_cell(0, 8, line.strip())
pdf4.output("mock_data/mock_msme_certificate.pdf")
print("✅ Created mock_data/mock_msme_certificate.pdf")

print("\n🎉 All mock data created in /mock_data folder!")
print("Use these files to demo the full pipeline to judges.")