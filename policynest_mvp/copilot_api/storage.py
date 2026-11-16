"""Document Storage and Upload Security Engine for PolicyNest.

Enforces:
1. Strict magic-byte detection (PNG, JPEG, WebP, PDF).
2. Explicit rejection of executable binaries (PE, ELF, Mach-O) and script vectors.
3. File size constraints (min 1KB, max 5MB).
4. Pure standard library image dimension extraction (PNG, JPEG, WebP).
5. Immutable content-addressable storage via SHA-256 digest.
6. Path traversal prevention during storage and retrieval.
"""
import hashlib
import os
import struct
from pathlib import Path
from typing import Dict, Optional, Tuple

from config import (
    ALLOWED_MIME_TYPES,
    MAX_DOCUMENT_SIZE,
    MIN_DOCUMENT_SIZE,
    get_storage_dir,
)

# Known Magic Byte Signatures
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_PDF = b"%PDF-"
MAGIC_RIFF = b"RIFF"
MAGIC_WEBP = b"WEBP"

# Dangerous Executable / Script Signatures to explicitly reject
DANGEROUS_SIGNATURES = [
    (b"MZ", "Executable (Windows PE)"),
    (b"\x7fELF", "Executable (Linux ELF)"),
    (b"\xca\xfe\xba\xbe", "Compiled Class (Java)"),
    (b"\xfe\xed\xfa\xce", "Executable (Mach-O 32-bit)"),
    (b"\xfe\xed\xfa\xcf", "Executable (Mach-O 64-bit)"),
    (b"\xce\xfa\xed\xfe", "Executable (Mach-O little-endian 32)"),
    (b"\xcf\xfa\xed\xfe", "Executable (Mach-O little-endian 64)"),
    (b"#!", "Shell Script"),
    (b"<?php", "PHP Script"),
    (b"<script", "HTML/JavaScript Payload"),
    (b"<!doctype html", "HTML Document"),
    (b"<html", "HTML Document"),
]


def detect_mime_type(content: bytes) -> str:
    """Identify MIME type strictly from content magic bytes."""
    if not content or len(content) < 4:
        raise ValueError("unrecognized_file_format")

    # Check for dangerous malicious content first
    header_lower = content[:64].lower()
    for sig, desc in DANGEROUS_SIGNATURES:
        if content.startswith(sig) or (sig in header_lower and len(sig) > 3):
            raise ValueError(f"dangerous_file_type_detected:{desc}")

    # PNG
    if content.startswith(MAGIC_PNG):
        return "image/png"

    # JPEG
    if content.startswith(MAGIC_JPEG):
        return "image/jpeg"

    # PDF
    if content.startswith(MAGIC_PDF):
        return "application/pdf"

    # WebP
    if len(content) >= 12 and content[:4] == MAGIC_RIFF and content[8:12] == MAGIC_WEBP:
        return "image/webp"

    raise ValueError("unsupported_file_format")


def extract_image_dimensions(content: bytes, mime_type: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract width and height using pure standard library parsing."""
    if mime_type == "application/pdf":
        return None, None

    try:
        # PNG: bytes 16..24 contain 4-byte width and 4-byte height
        if mime_type == "image/png" and len(content) >= 24:
            width, height = struct.unpack(">II", content[16:24])
            return width, height

        # JPEG: Walk markers to locate Start of Frame (SOF0, SOF1, SOF2)
        if mime_type == "image/jpeg" and len(content) > 4:
            idx = 2
            length = len(content)
            while idx < length - 9:
                if content[idx] != 0xFF:
                    idx += 1
                    continue
                marker = content[idx + 1]
                # SOF0 (0xC0), SOF1 (0xC1), SOF2 (0xC2)
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", content[idx + 5 : idx + 9])
                    return w, h
                # Skip marker segment
                segment_len = struct.unpack(">H", content[idx + 2 : idx + 4])[0]
                idx += 2 + segment_len

        # WebP:
        if mime_type == "image/webp" and len(content) >= 30:
            format_tag = content[12:16]
            if format_tag == b"VP8 ":
                # Lossy VP8
                w, h = struct.unpack("<HH", content[26:30])
                return w & 0x3FFF, h & 0x3FFF
            elif format_tag == b"VP8L":
                # Lossless VP8L
                b0, b1, b2, b3 = content[21:25]
                w = 1 + (((b1 & 0x3F) << 8) | b0)
                h = 1 + (((b3 & 0xF) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
                return w, h
    except Exception:
        pass

    return None, None


def validate_file_content(content: bytes, declared_mime: Optional[str] = None) -> Dict:
    """Validate content size, security signatures, and MIME type."""
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("file_content_must_be_bytes")

    file_size = len(content)
    if file_size < MIN_DOCUMENT_SIZE:
        raise ValueError("file_too_small")
    if file_size > MAX_DOCUMENT_SIZE:
        raise ValueError("file_size_exceeds_limit")

    detected_mime = detect_mime_type(content)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValueError("unallowed_document_type")

    if declared_mime and declared_mime != detected_mime:
        # If client declares png but uploads jpeg, accept detected_mime as ground truth
        pass

    width, height = extract_image_dimensions(content, detected_mime)

    sha256_hash = hashlib.sha256(content).hexdigest()

    return {
        "mime_type": detected_mime,
        "file_size": file_size,
        "sha256_hash": sha256_hash,
        "width": width,
        "height": height,
    }


def store_document_file(content: bytes, declared_mime: Optional[str] = None) -> Dict:
    """Validate and atomically persist document bytes into immutable storage."""
    meta = validate_file_content(content, declared_mime)
    storage_dir = get_storage_dir()

    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    ext = ext_map.get(meta["mime_type"], ".bin")
    file_name = f"{meta['sha256_hash']}{ext}"
    target_path = storage_dir / file_name

    # Atomic write to temporary file first
    temp_path = storage_dir / f".tmp_{meta['sha256_hash']}_{os.getpid()}"
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
        # Rename is atomic in POSIX and modern Windows
        if target_path.exists():
            temp_path.unlink()
        else:
            temp_path.replace(target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    meta["storage_path"] = str(target_path.resolve())
    meta["file_name"] = file_name
    return meta


def read_document_file(storage_path_str: str) -> bytes:
    """Securely retrieve document bytes while preventing path traversal."""
    storage_dir = get_storage_dir().resolve()
    target = Path(storage_path_str).resolve()

    # Prevent directory traversal attacks
    try:
        target.relative_to(storage_dir)
    except ValueError:
        raise PermissionError("access_denied_invalid_storage_path")

    if not target.exists() or not target.is_file():
        raise FileNotFoundError("document_file_not_found")

    with open(target, "rb") as f:
        return f.read()
