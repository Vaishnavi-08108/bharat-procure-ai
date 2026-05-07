import re
from typing import List, Optional

from .schemas import BidderDocument


def _addresses_match(addr1: Optional[str], addr2: Optional[str]) -> bool:
    """Fuzzy address match; normalize case and whitespace."""
    if addr1 is None or addr2 is None:
        return True
    a1 = " ".join(addr1.lower().split())
    a2 = " ".join(addr2.lower().split())
    return a1[:30] == a2[:30]


def run_cross_document_audit(bidder: BidderDocument) -> List[str]:
    """
    Returns a list of integrity flag strings.
    Empty list means clean. Non-empty means something needs human review.
    """
    flags = []

    if not _addresses_match(bidder.gst_registered_address, bidder.pan_registered_address):
        flags.append(
            f"ADDRESS MISMATCH: GST address '{bidder.gst_registered_address}' "
            f"differs from PAN address '{bidder.pan_registered_address}'"
        )

    if not _addresses_match(bidder.gst_registered_address, bidder.msme_registered_address):
        flags.append("ADDRESS MISMATCH: GST address does not match MSME certificate address")

    if bidder.pan_number and not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", bidder.pan_number):
        flags.append(f"INVALID FORMAT: PAN number '{bidder.pan_number}' has invalid format")

    if bidder.gst_number and bidder.pan_number and bidder.pan_number not in bidder.gst_number:
        flags.append(
            "INTEGRITY FAILURE: GST number does not contain PAN number - "
            "possible document forgery or mismatch"
        )

    return flags
