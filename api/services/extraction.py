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
    checklist_with_fields: list,
) -> str:
    """
    Builds the Claude system prompt dynamically from per-document field config.

    Args:
        process_name:         Process name e.g. RSA Mortgage Application
        checklist_with_fields: List of dicts:
            {
                "id": int,
                "name": str,
                "category": str,
                "fields": [{"name": str, ...}]  # empty list if none configured
            }

    Returns:
        System prompt string for Claude.
    """
    # Build checklist with per-document fields
    checklist_lines = []
    for doc in checklist_with_fields:
        line = f"{doc['id']}. {doc['name']} ({doc['category']})"
        if doc["fields"]:
            field_names = ", ".join(f["name"] for f in doc["fields"])
            line += f"\n   Extract: {field_names}"
        else:
            line += "\n   Extract: classify only — no fields configured"
        checklist_lines.append(line)

    checklist_str = "\n".join(checklist_lines)

    # Build extractedFields template — only fields for the matched doc type
    # We tell Claude to only include fields for the document it matched

    return f"""
    You are a document analyst for a Nigerian document processing platform.
    You receive document text or images and must classify and extract fields.

    Process: {process_name}

    Document checklist — classify this document and extract ONLY the fields
    listed for the matched document type:

    {checklist_str}

    Respond ONLY with valid JSON — no markdown, no backticks, no explanation.

    Return this exact structure:
    {{
        "documentType": "<matched name from checklist or 'Unknown'>",
        "matchedDocId": <integer id from checklist or null>,
        "category": "<category string>",
        "confidence": <integer 0-100>,
        "summary": "<2 sentence summary of the document>",
        "extractedFields": {{
            "<field name>": {{"value": "<string or null>", "confidence": <0-100>}}
        }},
        "flags": [
            {{
                "type": "ok|warn|err",
                "message": "<message>"
            }}
        ]
    }}

    Rules:
    - ONLY extract the fields listed under the matched document type above
    - Do NOT extract fields from other document types
    - Set value to null for any listed field not found in this document
    - matchedDocId must exactly match an id from the checklist
    - If the document does not match any checklist item, set documentType
      to 'Unknown', matchedDocId to null, confidence to 0
    - Nigerian documents: NIN slips (NIMC), BVN letters, CAC certificates,
      WAEC/NECO results, CBN bank statements, voters cards, international
      passports, utility bills, tenancy agreements, offer letters are all common
    - Flag expired documents with type "err"
    - Flag low-quality or unclear fields with type "warn"
    - Flag successfully verified fields with type "ok"
"""


def classify_and_extract(
    process_name: str,
    checklist_with_fields: list,
    ocr_text: str = "",
    file_bytes: bytes = b"",
    mime_type: str = "",
) -> dict:
    """
    Classify a document and extract per-document configured fields using Claude.

    Args:
        process_name:          Name of the process
        checklist_with_fields: List of dicts with id, name, category, fields
                               Each "fields" list contains {"name": str, ...}
                               Empty fields list = classify only, no extraction
        ocr_text:              Raw text from Azure DocInt (text mode)
        file_bytes:            Raw file bytes (vision mode fallback)
        mime_type:             MIME type of the file (vision mode fallback)

    Returns:
        Dict with documentType, matchedDocId, confidence,
        extractedFields, flags, summary.

    Raises:
        ValueError: If checklist_with_fields is empty or no content provided.
    """
    import anthropic

    from config.settings import settings

    if not checklist_with_fields:
        raise ValueError(
            "checklist_with_fields is empty — no documents configured "
            "for this process."
        )

    if not ocr_text and not (file_bytes and mime_type):
        raise ValueError(
            "Either ocr_text or both file_bytes and mime_type must be provided"
        )

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    system_prompt = _build_system_prompt(
        process_name=process_name,
        checklist_with_fields=checklist_with_fields,
    )

    checklist_str = "\n".join(
        f"{d['id']}. {d['name']} ({d['category']})" for d in checklist_with_fields
    )

    total_fields = sum(len(d["fields"]) for d in checklist_with_fields)

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
            f"{len(checklist_with_fields)} checklist items, "
            f"{total_fields} total fields)"
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
            f"{total_fields} total fields)"
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
