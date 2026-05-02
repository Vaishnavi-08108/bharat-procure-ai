from typing import Optional, List
from .schemas import BidderDocument
from typing import List

def _addresses_match(addr1: Optional[str], addr2: Optional[str]) -> bool:
    """Fuzzy address match — normalise case and whitespace."""
    if addr1 is None or addr2 is None:
        return True  # Can't compare, don't flag
    a1 = " ".join(addr1.lower().split())
    a2 = " ".join(addr2.lower().split())
    # Check if key tokens match (first 30 chars is a simple heuristic)
    return a1[:30] == a2[:30]

def run_cross_document_audit(bidder: BidderDocument) -> List[str]:
    """
    Returns a list of integrity flag strings.
    Empty list = clean. Non-empty = something needs human review.
    """
    flags = []

    # Check 1: GST address vs PAN address
    if not _addresses_match(bidder.gst_registered_address, bidder.pan_registered_address):
        flags.append(
            f"ADDRESS MISMATCH: GST address '{bidder.gst_registered_address}' "
            f"differs from PAN address '{bidder.pan_registered_address}'"
        )

    # Check 2: GST address vs MSME address
    if not _addresses_match(bidder.gst_registered_address, bidder.msme_registered_address):
        flags.append(
            f"ADDRESS MISMATCH: GST address does not match MSME certificate address"
        )

    # Check 3: PAN number format (basic validation)
    if bidder.pan_number:
        import re
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", bidder.pan_number):
            flags.append(f"INVALID FORMAT: PAN number '{bidder.pan_number}' has invalid format")

    # Check 4: GST number contains PAN (GST is derived from PAN — standard rule)
    if bidder.gst_number and bidder.pan_number:
        if bidder.pan_number not in bidder.gst_number:
            flags.append(
                f"INTEGRITY FAILURE: GST number does not contain PAN number — "
                f"possible document forgery or mismatch"
            )

    return flags