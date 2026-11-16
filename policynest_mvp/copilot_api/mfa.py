"""RFC 6238 TOTP (Time-based One-Time Password) and Recovery Code Engine.

Implemented using only standard library (base64, hashlib, hmac, secrets, struct, time).
Zero external dependencies.
Provides:
- 32-character Base32 secret generation for authenticator apps (Google Authenticator, Authy, Microsoft Authenticator)
- otpauth:// URI formatting for QR code display
- 6-digit TOTP verification with ±30s clock drift tolerance
- Secure, single-use alphanumeric backup recovery codes (hashed in database)
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time


def generate_totp_secret():
    """Generate a random 160-bit (20 byte) Base32 secret."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").replace("=", "")


def get_totp_uri(secret, email, issuer="PolicyNest"):
    """Format standard otpauth URI for authenticator app configuration."""
    clean_secret = secret.replace(" ", "").upper()
    return f"otpauth://totp/{issuer}:{email}?secret={clean_secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def generate_totp_code(secret, timestamp=None, step=30):
    """Generate the current 6-digit TOTP code for a secret."""
    t = int((timestamp if timestamp is not None else time.time()) / step)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code_int % 1_000_000:06d}"


def verify_totp(secret, code, window=1, step=30):
    """Verify a user-provided 6-digit TOTP code with drift tolerance (window=1 allows ±30s)."""
    if not secret or not code:
        return False
    clean_code = str(code).strip().replace(" ", "")
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False
    now = time.time()
    for drift in range(-window, window + 1):
        if hmac.compare_digest(clean_code, generate_totp_code(secret, now + drift * step, step)):
            return True
    return False


def generate_recovery_codes(count=8):
    """Generate human-readable, high-entropy recovery codes like 'ABCD-1234'."""
    codes = []
    for _ in range(count):
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        codes.append(f"{part1}-{part2}")
    return codes


def hash_recovery_code(code):
    """SHA-256 hash a normalized recovery code for safe persistence."""
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_and_consume_recovery_code(code, hashed_codes_list):
    """Check if code matches any in the list; returns (matched: bool, remaining_hashes: list)."""
    target = hash_recovery_code(code)
    for i, stored in enumerate(hashed_codes_list):
        if hmac.compare_digest(target, stored):
            remaining = hashed_codes_list[:i] + hashed_codes_list[i + 1 :]
            return True, remaining
    return False, hashed_codes_list
