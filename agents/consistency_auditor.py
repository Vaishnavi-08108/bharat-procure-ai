import re


def _normalize_value(value: str | None, field_name: str) -> str:
    if not value:
        return ""
    normalized = value.lower()
    if field_name == "entity_name":
        normalized = normalized.replace("private limited", "pvt ltd")
        normalized = normalized.replace("private ltd", "pvt ltd")
    if field_name == "address":
        normalized = re.sub(r"\b\d{6}\b", "", normalized)
    return re.sub(r"[^a-z0-9]", "", normalized)


def _field_values(documents: list[dict], field_name: str) -> list[str]:
    values = []
    for document in documents:
        value = document.get(field_name)
        if not value and isinstance(document.get("key_fields"), dict):
            value = document["key_fields"].get(field_name)
        if value:
            values.append(str(value).strip())
    return values


def audit_consistency(documents: list[dict]) -> dict:
    """
    Deterministic cross-document consistency audit.
    """
    if not documents:
        return {"error": "No documents provided"}

    checks = []
    critical_flags = []

    for field_name, label in (("entity_name", "entity_name"), ("address", "address")):
        values = _field_values(documents, field_name)
        normalized_values = {
            _normalize_value(value, field_name)
            for value in values
            if _normalize_value(value, field_name)
        }

        if not values:
            status = "MISSING"
            note = f"No {label} found across submitted documents"
        elif len(normalized_values) == 1:
            status = "MATCH"
            note = f"{label.replace('_', ' ').title()} matches across documents"
        else:
            status = "MISMATCH"
            note = f"{label.replace('_', ' ').title()} differs across documents"
            critical_flags.append(note)

        checks.append(
            {
                "field": field_name,
                "status": status,
                "values_found": values,
                "note": note,
            }
        )

    low_confidence_docs = [
        document.get("source_filename") or document.get("document_type") or "Unknown document"
        for document in documents
        if document.get("needs_human_review")
    ]
    if low_confidence_docs:
        critical_flags.append(
            "Low confidence documents need officer review: " + ", ".join(low_confidence_docs)
        )

    has_mismatch = any(check["status"] == "MISMATCH" for check in checks)
    has_missing = any(check["status"] == "MISSING" for check in checks)
    needs_human_review = bool(low_confidence_docs or has_missing or has_mismatch)

    if has_mismatch:
        overall_status = "INCONSISTENT"
    elif needs_human_review:
        overall_status = "NEEDS_REVIEW"
    else:
        overall_status = "CONSISTENT"

    return {
        "overall_status": overall_status,
        "checks": checks,
        "critical_flags": critical_flags,
        "needs_human_review": needs_human_review,
    }
