"""File handling utilities for OpenRAG"""

import os
import re
import tempfile
import unicodedata
from contextlib import contextmanager
from typing import Optional
from uuid import uuid4


@contextmanager
def auto_cleanup_tempfile(suffix: Optional[str] = None, prefix: Optional[str] = None, dir: Optional[str] = None):
    """
    Context manager for temporary files that automatically cleans up.

    Unlike tempfile.NamedTemporaryFile with delete=True, this keeps the file
    on disk for the duration of the context, making it safe for async operations.

    Usage:
        with auto_cleanup_tempfile(suffix=".pdf") as tmp_path:
            # Write to the file
            with open(tmp_path, 'wb') as f:
                f.write(content)
            # Use tmp_path for processing
            result = await process_file(tmp_path)
        # File is automatically deleted here

    Args:
        suffix: Optional file suffix/extension (e.g., ".pdf")
        prefix: Optional file prefix
        dir: Optional directory for temp file

    Yields:
        str: Path to the temporary file
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    try:
        os.close(fd)  # Close the file descriptor immediately
        yield path
    finally:
        # Always clean up, even if an exception occurred
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            # Silently ignore cleanup errors
            pass


def safe_unlink(path: str) -> None:
    """
    Safely delete a file, ignoring errors if it doesn't exist.

    Args:
        path: Path to the file to delete
    """
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        # Silently ignore errors
        pass


def normalize_path(path: str) -> str:
    """Normalize path separators and duplicate/trailing markers."""
    normalized = (path or "").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if normalized.endswith("/") and normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def get_file_extension(mimetype: str) -> str:
    """Get file extension based on MIME type"""
    mime_to_ext = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/vnd.ms-powerpoint": ".ppt",
        "text/plain": ".txt",
        "text/html": ".html",
        "application/rtf": ".rtf",
        "application/vnd.google-apps.document": ".pdf",  # Exported as PDF
        "application/vnd.google-apps.presentation": ".pdf",
        "application/vnd.google-apps.spreadsheet": ".pdf",
    }
    return mime_to_ext.get(mimetype, ".bin")


def _transliterate_cyrillic(text: str) -> str:
    """Transliterate basic Russian Cyrillic to Latin. Other chars unchanged."""
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    return "".join(mapping.get(c.lower(), c) for c in text)


def make_safe_storage_filename(filename: str) -> str:
    """
    Produce an ASCII-only storage filename for Langflow/ingestion.
    Allowed chars: a-z A-Z 0-9 . _ -
    Spaces -> _, Cyrillic transliterated, other non-ASCII replaced or fallback to file_<uuid>.ext
    """
    if not filename or not filename.strip():
        return f"file_{uuid4().hex}.bin"
    base, ext = os.path.splitext(filename)
    base = base.replace(" ", "_")
    base = _transliterate_cyrillic(base)
    base_ascii = base.encode("ascii", "replace").decode("ascii")
    base_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "_", base_ascii)
    base_ascii = re.sub(r"_+", "_", base_ascii).strip("._-")
    ext_ascii = _transliterate_cyrillic(ext)
    ext_ascii = ext_ascii.encode("ascii", "replace").decode("ascii")
    ext_ascii = re.sub(r"[^a-zA-Z0-9.]+", "", ext_ascii)
    if not ext_ascii or not ext_ascii.startswith("."):
        ext_ascii = ".bin"
    if not base_ascii:
        base_ascii = f"file_{uuid4().hex}"
    return base_ascii + ext_ascii


def clean_connector_filename(filename: str, mimetype: str) -> str:
    """Clean filename and ensure correct extension"""
    suffix = get_file_extension(mimetype)
    clean_name = filename.replace(" ", "_").replace("/", "_")
    if not clean_name.lower().endswith(suffix.lower()):
        return clean_name + suffix
    return clean_name