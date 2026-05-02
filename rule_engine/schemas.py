from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class VerdictStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HUMAN_REVIEW = "HUMAN_REVIEW"

class TenderRequirements(BaseModel):
    tender_id: str
    min_turnover_lakhs: float
    min_experience_years: int
    required_certificates: List[str]
    max_bid_validity_days: int
    emd_required_lakhs: float

class BidderDocument(BaseModel):
    bidder_id: str
    bidder_name: str
    annual_turnover_lakhs: Optional[float] = None
    turnover_confidence: float = 1.0
    years_of_experience: Optional[int] = None
    experience_confidence: float = 1.0
    certificates_present: dict[str, bool] = Field(default_factory=dict)
    gst_registered_address: Optional[str] = None
    pan_registered_address: Optional[str] = None
    msme_registered_address: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    emd_submitted_lakhs: Optional[float] = None

class CheckResult(BaseModel):
    check_name: str
    status: VerdictStatus
    reason: str
    extracted_value: Optional[str] = None
    required_value: Optional[str] = None
    confidence: float = 1.0

class BidderVerdict(BaseModel):
    bidder_id: str
    bidder_name: str
    overall_status: VerdictStatus
    checks: List[CheckResult]
    audit_flags: List[str]
    model_version: str = "1.0.0"
    timestamp: str
