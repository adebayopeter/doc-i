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


# ── Extraction prompt ──────────────────────────────────────────────────────────
def _build_system_prompt(
    process_name: str,
    checklist: list,
    extraction_fields: list,
) -> str:
    """
    Builds the Claude system prompt dynamically from configured fields.

    Args:
        process_name:      Name of the process e.g. RSA Mortgage Application
        checklist:         List of dicts with id, name, category
        extraction_fields: List of dicts with at least {"name": str}

    Returns:
        System prompt string for Claude.
    """
    checklist_str = "\n".join(
        f"{d['id']}. {d['name']} ({d['category']})" for d in checklist
    )

    # Build only the fields configured for this process
    fields_template = "\n".join(
        f'            "{f["name"]}":             '
        f'{{"value": "<string or null>", "confidence": <0-100>}},'
        for f in extraction_fields
    )

    return f"""
    You are a document analyst for a Nigerian document processing platform.
    You receive document text or images and must classify and extract fields.

    Process: {process_name}

    Required document checklist: {checklist_str}

    Respond ONLY with valid JSON — no markdown, no backticks, no explanation.

    Return this exact structure:
    {{
        "documentType": "<matched name from checklist or 'Unknown'>",
        "matchedDocId": <integer id from checklist or null>,
        "category": "<category string>",
        "confidence": <integer 0-100>,
        "summary": "<2 sentence summary of the document>",
        "extractedFields": {{
        {fields_template}
        }},
        "flags": [
            {{
                "type": "ok|warn|err",
                "message": "<message>"
            }}
        ]
    }}

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
    extraction_fields: list,
    ocr_text: str = "",
    file_bytes: bytes = b"",
    mime_type: str = "",
) -> dict:
    """
    Classify a document and extract configured fields using Claude.

    Args:
        process_name:       Name of the process
        document_checklist: List of dicts — id, name, category
        extraction_fields:  List of dicts — must have at least {"name": str}
                            Must not be empty — caller is responsible for
                            checking this before calling.
        ocr_text:           Raw text from Azure DocInt (text mode)
        file_bytes:         Raw file bytes (vision mode fallback)
        mime_type:          MIME type of the file (vision mode fallback)

    Returns:
        Dict with documentType, matchedDocId, confidence,
        extractedFields, flags, summary.

    Raises:
        ValueError: If extraction_fields is empty or no content provided.
    """
    import anthropic

    from config.settings import settings

    if not extraction_fields:
        raise ValueError(
            "extraction_fields is empty — extraction is disabled for this "
            "process. Configure extraction fields before uploading documents."
        )

    if not ocr_text and not (file_bytes and mime_type):
        raise ValueError(
            "Either ocr_text or both file_bytes and mime_type must be provided"
        )

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    system_prompt = _build_system_prompt(
        process_name=process_name,
        checklist=document_checklist,
        extraction_fields=extraction_fields,
    )

    checklist_str = "\n".join(
        f"{d['id']}. {d['name']} ({d['category']})" for d in document_checklist
    )

    if ocr_text:
        # ── Mode A: text mode — Azure extracted text  ──────────────────────────────────────────────
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
            f"({len(ocr_text)} chars, "
            f"{len(document_checklist)} checklist items), "
            f"{len(extraction_fields)} fields)"
        )

    else:
        # ── Mode B: vision mode — raw file sent to Claude ──────────────────
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
            f"{len(extraction_fields)} fields)"
        )

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_TOKENS,
        system=system_prompt,
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
