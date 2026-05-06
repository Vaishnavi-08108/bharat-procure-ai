"""
MEMBER 2 — Audit Logger
Saves every AI + officer decision to a JSON file.
This is what makes the system legally auditable
for government use.
"""

import json
import os
from datetime import datetime


AUDIT_FILE = "audit_trail.json"


def _load_log() -> list:
    """Load existing audit log from file."""
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_log(entries: list):
    """Save audit log to file."""
    with open(AUDIT_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def log_action(
    action: str,
    agent: str,
    input_summary: str,
    result_summary: str,
    confidence: float = None,
    model_version: str = "gemini-1.5-flash",
    officer_id: str = None,
    tender_id: str = None,
    bidder_name: str = None
):
    """
    Logs a single action to the audit trail.
    
    action: what happened e.g. "tender_analyzed"
    agent: which agent did it e.g. "TenderAnalyst"
    input_summary: brief description of input
    result_summary: brief description of result
    confidence: 0.0 to 1.0 if applicable
    model_version: AI model used
    officer_id: if a human officer took this action
    tender_id: tender reference number
    bidder_name: bidder being evaluated
    """
    entries = _load_log()

    entry = {
        "entry_id": f"LOG-{len(entries)+1:04d}",
        "timestamp": datetime.now().isoformat(),
        "timestamp_readable": datetime.now().strftime(
            "%d-%b-%Y %H:%M:%S IST"
        ),
        "tender_id": tender_id or "UNKNOWN",
        "bidder_name": bidder_name or "UNKNOWN",
        "agent": agent,
        "action": action,
        "input_summary": input_summary,
        "result_summary": result_summary,
        "confidence_score": confidence,
        "model_version": model_version,
        "officer_id": officer_id,
        "entry_type": "HUMAN" if officer_id else "AI"
    }

    entries.append(entry)
    _save_log(entries)

    return entry


def get_full_log() -> list:
    """Returns complete audit trail."""
    return _load_log()


def get_log_for_tender(tender_id: str) -> list:
    """Returns all log entries for a specific tender."""
    return [
        e for e in _load_log()
        if e.get("tender_id") == tender_id
    ]


def get_log_for_bidder(bidder_name: str) -> list:
    """Returns all log entries for a specific bidder."""
    return [
        e for e in _load_log()
        if e.get("bidder_name") == bidder_name
    ]


def get_hitl_entries() -> list:
    """Returns only entries that required human review."""
    return [
        e for e in _load_log()
        if "HITL" in e.get("action", "").upper()
        or "HUMAN" in e.get("entry_type", "").upper()
    ]