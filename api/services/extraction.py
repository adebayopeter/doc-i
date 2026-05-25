"""
Extraction service — Claude AI document classification and field extraction.

Takes either:
  A) Plain text from Azure DocInt OCR (preferred — cheaper, faster)
  B) Raw file bytes (fallback when Azure not configured)

Returns a structured dict with document type, confidence, extracted fields,
flags, and a summary — all fields needed to update the SubmissionDocument.
"""

import json

from config.logging import get_logger

logger = get_logger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────
# Instructs Claude on the response format and Nigerian document context.
# Nigerian-specific documents are called out explicitly so Claude
# handles NIN slips, BVN letters, CAC certificates correctly.

_SYSTEM_PROMPT = """
    You are a document analyst for a Nigerian document processing platform.
    You receive document text or images and must classify and extract fields.

    Respond ONLY with valid JSON — no markdown, no backticks, no explanation.

    Return this exact structure:
    {
        "documentType": "<matched name from checklist or 'Unknown'>",
        "matchedDocId": <integer id from checklist or null>,
        "category": "<category string>",
        "confidence": <integer 0-100>,
        "summary": "<2 sentence summary of the document>",
        "extractedFields": {
            "Full Name":             {"value": "<string or null>", "confidence": <0-100>},
            "Date of Birth":         {"value": "<YYYY-MM-DD or null>", "confidence": <0-100>},
            "ID / Reference Number": {"value": "<string or null>", "confidence": <0-100>},
            "NIN":                   {"value": "<11-digit string or null>", "confidence": <0-100>},
            "BVN":                   {"value": "<11-digit string or null>", "confidence": <0-100>},
            "Address":               {"value": "<string or null>", "confidence": <0-100>},
            "Expiry Date":           {"value": "<YYYY-MM-DD or null>", "confidence": <0-100>},
            "Issuing Authority":     {"value": "<string or null>", "confidence": <0-100>},
            "Employer Name":         {"value": "<string or null>", "confidence": <0-100>},
            "Annual Income":         {"value": "<string or null>", "confidence": <0-100>},
            "Account Number":        {"value": "<10-digit string or null>", "confidence": <0-100>},
            "Bank Name":             {"value": "<string or null>", "confidence": <0-100>},
            "Sort Code":             {"value": "<string or null>", "confidence": <0-100>},
            "Policy Number":         {"value": "<string or null>", "confidence": <0-100>},
            "Property Address":      {"value": "<string or null>", "confidence": <0-100>},
            "Property Value":        {"value": "<string or null>", "confidence": <0-100>}
        },
        "flags": [
            {
                "type": "ok|warn|err",
                "message": "<message>"
            }
        ]
    }

    Rules:
    - Set value to null for any field not found in the document
    - Only include fields relevant to this document type
    - matchedDocId must exactly match an id from the checklist
    - Nigerian documents: NIN slips (NIMC), BVN letters, CAC certificates,
      WAEC/NECO results, CBN bank statements, voters cards, international passports,
      utility bills, tenancy agreements, offer letters are all common
    - Flag expired documents with type "err"
    - Flag low-quality or unclear fields with type "warn"
    - Flag successfully verified fields with type "ok"
"""


def classify_and_extract(
    process_name: str,
    document_checklist: list,
    ocr_text: str = "",
    file_bytes: bytes = b"",
    mime_type: str = "",
) -> dict:
    """
    Classify a document and extract structured fields using Claude.

    Mode A — text mode (when ocr_text is provided):
        Cheaper and faster. Azure DocInt pre-extracted the text.
        Claude reads the text and extracts fields.

    Mode B — vision mode (when file_bytes and mime_type are provided):
        Used when Azure DocInt is not configured.
        Claude reads the raw image or PDF directly.

    Args:
        process_name:       Name of the process e.g. "RSA Mortgage"
        document_checklist: List of {"id": int, "name": str, "category": str}
        ocr_text:           Pre-extracted text from Azure DocInt (optional)
        file_bytes:         Raw file bytes for vision mode (optional)
        mime_type:          MIME type for vision mode (optional)

    Returns:
        Dict with documentType, matchedDocId, confidence, extractedFields,
        flags, and summary.

    Raises:
        ValueError: If neither ocr_text nor file_bytes+mime_type provided
        Exception:  If Claude API call fails
    """
    import anthropic

    from config.settings import settings

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    checklist_str = "\n".join(
        f"{d['id']}. {d['name']} ({d['category']})" for d in document_checklist
    )

    if ocr_text:
        # ── Mode A: text mode ──────────────────────────────────────────────
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Process: {process_name}\n\n"
                    f"Required document checklist:\n{checklist_str}\n\n"
                    f"Extracted document text:\n{ocr_text}"
                ),
            }
        ]
        logger.debug(
            f"Claude extraction — text mode "
            f"({len(ocr_text)} chars, {len(document_checklist)} checklist items)"
        )

    elif file_bytes and mime_type:
        # ── Mode B: vision mode ────────────────────────────────────────────
        import base64

        doc_type = "document" if mime_type == "application/pdf" else "image"
        user_content = [
            {
                "type": doc_type,
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64.b64encode(file_bytes).decode(),
                },
            },
            {
                "type": "text",
                "text": (
                    f"Process: {process_name}\n\n"
                    f"Required document checklist:\n{checklist_str}"
                ),
            },
        ]
        logger.debug(
            f"Claude extraction — vision mode "
            f"({len(file_bytes)} bytes, {mime_type})"
        )
    else:
        raise ValueError(
            "Either ocr_text or both file_bytes and mime_type must be provided"
        )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = response.content[0].text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}\nRaw: {raw_text[:200]}")
        raise ValueError(f"Claude returned invalid JSON: {e}")

    logger.info(
        f"Claude classified: '{result.get('documentType')}' "
        f"confidence={result.get('confidence')}%"
    )
    return result
