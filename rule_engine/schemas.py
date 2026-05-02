from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class VerdictStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HUMAN_REVIEW = "HUMAN_REVIEW"  # HITL trigger

class TenderRequirements(BaseModel):
    """Extracted from the tender PDF by Member 1's Tender Analyst agent."""
    tender_id: str
    min_turnover_lakhs: float          # e.g. 500.0 (Rs. 5 crore)
    min_experience_years: int          # e.g. 3
    required_certificates: List[str]   # e.g. ["GST", "PAN", "MSME", "ISO_9001"]
    max_bid_validity_days: int         # e.g. 180
    emd_required_lakhs: float          # Earnest Money Deposit

class BidderDocument(BaseModel):
    """Structured data extracted from one bidder's documents by Member 1's Vision agent."""
    bidder_id: str
    bidder_name: str

    # Financial
    annual_turnover_lakhs: Optional[float] = None
    turnover_confidence: float = 1.0   # 0.0–1.0, set by Vision agent

    # Experience
    years_of_experience: Optional[int] = None
    experience_confidence: float = 1.0

    # Certificates present (True/False per cert)
    certificates_present: dict[str, bool] = Field(default_factory=dict)

    # Cross-document fields for audit
    gst_registered_address: Optional[str] = None
    pan_registered_address: Optional[str] = None
    msme_registered_address: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None

    # EMD
    emd_submitted_lakhs: Optional[float] = None

class CheckResult(BaseModel):
    """Result of one individual rule check."""
    check_name: str
    status: VerdictStatus
    reason: str
    extracted_value: Optional[str] = None
    required_value: Optional[str] = None
    confidence: float = 1.0

class BidderVerdict(BaseModel):
    """Final verdict for one bidder — this is what Member 3 displays."""
    bidder_id: str
    bidder_name: str
    overall_status: VerdictStatus
    checks: List[CheckResult]
    audit_flags: List[str]             # Cross-document mismatches
    model_version: str = "1.0.0"
    timestamp: str