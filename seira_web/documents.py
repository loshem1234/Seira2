"""seira_web.documents — extracting readable text from an uploaded file.

Supported now: .txt, .md/.markdown (read as-is), .pdf (text layer,
via pypdf). NOT supported yet, and stated plainly rather than faked:
OCR for scanned/image-only PDFs. A PDF with no extractable text layer
returns found=False with an honest explanation, never a wall of
mojibake or a silent empty result. OCR is a real, larger build (a
rendering step + tesseract) that belongs as its own Instrument
paradigm in a later phase, not a corner cut here.
"""

from __future__ import annotations

from typing import Any, Dict

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100MB, as requested
SUPPORTED_EXTENSIONS = (".txt", ".md", ".markdown", ".pdf")


def extract_text(filename: str, raw: bytes) -> Dict[str, Any]:
    """Return {"ok": True, "text": ...} or {"ok": False, "error": ...}.
    Never raises: callers (the upload endpoint, tests) get a clean
    result either way."""
    name = filename.lower()
    if name.endswith((".txt", ".md", ".markdown")):
        try:
            return {"ok": True, "text": raw.decode("utf-8")}
        except UnicodeDecodeError:
            return {"ok": False, "error": "Document is not readable UTF-8 text."}

    if name.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    return {"ok": False,
                           "error": "This PDF is password-protected; "
                                    "remove the password and try again."}
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n\n".join(p for p in pages if p.strip())
            if not text.strip():
                return {"ok": False,
                       "error": "No extractable text found in this PDF. It may "
                                "be a scanned/image-only document — OCR for "
                                "that case isn't supported yet."}
            return {"ok": True, "text": text}
        except Exception as e:
            return {"ok": False, "error": f"Could not read this PDF ({e})."}

    return {"ok": False,
           "error": f"Unsupported file type. Seira currently reads "
                    f"{', '.join(SUPPORTED_EXTENSIONS)}."}
