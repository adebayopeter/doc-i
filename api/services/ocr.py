"""
OCR service - Azure Document Intelligence Read API.

Converts uploaded document bytes into clean plain text.
This is a pure text extraction step - no classification, no field parsing.
The extracted text is passed to Claude for intelligent field extraction.

If Azure DocInt is not configured (keys missing), returns empty string
and Claude falls back to processing the raw file bytes directly
"""

from config.logging import get_logger

logger = get_logger(__name__)


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    """
    Send document bytes to Azure DocInt Read model.
    Returns all text extracted from all pages as a single string.

    Falls back gracefully if Azure is not configured — the extraction
    service will then send the raw file to Claude as an image/document.

    Args:
        file_bytes: Raw bytes of the uploaded file
        mime_type:  MIME type e.g. application/pdf, image/jpeg

    Returns:
        Extracted text string, or empty string if Azure not configured
    """
    from config.settings import settings

    if not settings.AZURE_DOCINT_ENDPOINT or not settings.AZURE_DOCINT_KEY:
        logger.warning(
            "Azure DocInt not configured — skipping OCR pre-processing. "
            "Claude will process the raw file directly."
        )
        return ""

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=settings.AZURE_DOCINT_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_DOCINT_KEY),
        )

        poller = client.begin_analyze_document(
            "prebuilt-read",
            analyze_request=file_bytes,
            content_type=mime_type,
        )
        result = poller.result()

        pages_text = []
        for page in result.pages:
            lines = [line.content for line in (page.lines or [])]
            pages_text.append("\n".join(lines))

        full_text = "\n\n".join(pages_text)
        logger.debug(
            f"Azure DocInt extracted {len(full_text)} characters "
            f"from {len(result.pages)} page(s)"
        )
        return full_text

    except Exception as e:
        logger.error(f"Azure DocInt extraction failed: {e}")
        return ""
