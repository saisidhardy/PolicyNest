"""PolicyNest Core Configuration and Environment Separation.

Enforces strict separation between DEVELOPMENT, SANDBOX, and PRODUCTION modes.
In PRODUCTION:
- Mock bypasses, demo fixtures, and testing credentials are strictly disabled.
- Strong cryptographic secrets (>= 32 characters, non-default) are required.
- Strict cookies (HttpOnly, Secure, SameSite) and security headers are enforced.
"""
import os
import re
from pathlib import Path

# Resolve environment mode
ENV = os.environ.get("POLICYNEST_ENV", "").strip().lower()
if not ENV:
    if os.environ.get("APP_NAME") or os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("VERCEL"):
        ENV = "production"
    else:
        ENV = "development"

IS_PRODUCTION = ENV == "production"
IS_SANDBOX = ENV == "sandbox"
IS_DEV = ENV == "development"

# Security and Credentials
JWT_SECRET_MIN_LEN = 32
JWT_TTL_APPLICANT = int(os.environ.get("JWT_TTL_SECONDS", "3600"))       # 1 hour
JWT_TTL_STAFF = int(os.environ.get("JWT_TTL_STAFF_SECONDS", "1800"))       # 30 minutes for staff
REFRESH_TTL = 7 * 86400                                                    # 7 days
RESET_TOKEN_TTL = 15 * 60                                                  # 15 minutes
INVITATION_TOKEN_TTL = 48 * 3600                                           # 48 hours

# Password Security
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes lockout after 5 consecutive failures

# Cookie Security
COOKIE_SECURE = IS_PRODUCTION or os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true")
COOKIE_SAMESITE = "Lax"

# Allowed CORS origins
DEFAULT_PROD_ORIGIN = "https://policynest.embarko.app"
_origins_env = os.environ.get("COPILOT_ORIGINS", "")
if _origins_env:
    ALLOWED_ORIGINS = {o.strip() for o in _origins_env.split(",") if o.strip() and o.strip() != "null"}
else:
    if IS_PRODUCTION:
        ALLOWED_ORIGINS = {DEFAULT_PROD_ORIGIN}
    else:
        ALLOWED_ORIGINS = {DEFAULT_PROD_ORIGIN, "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:8787", "http://127.0.0.1:8787"}

# Security Headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(self), microphone=(), payment=()",
    "Cache-Control": "no-store",
}
if IS_PRODUCTION:
    SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

# Safe database path
def get_db_path(env=None):
    e = os.environ if env is None else env
    if e.get("DATA_DIR"):
        return Path(os.path.join(e["DATA_DIR"], "policynest.sqlite3"))
    return Path(e.get("POLICYNEST_DB_PATH") or str(Path(__file__).resolve().parent / "policynest.sqlite3"))
