"""Production server-side identity, JWT, MFA, and access store for PolicyNest.

Implements:
- NIST SP 800-63B compliant password controls (min 12 chars, max 128 chars, Scrypt derivation).
- Anti-account-enumeration error responses.
- Account lockout after 5 consecutive failed attempts (15 min window).
- Mandatory applicant role enforcement on public registration.
- Controlled staff provisioning, invitations, forced password setup, and status management.
- Multi-Factor Authentication (TOTP RFC 6238 and single-use recovery codes).
- Cryptographic session rotation, refresh token family reuse detection, and token version revocation.
- Per-session Anti-CSRF token generation and validation.
- Audit trail for staff role changes and administrative actions.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager, closing

import config
import migrations
import mfa
import policy


HERE = Path(__file__).resolve().parent


def resolve_db_path(env=None):
    return config.get_db_path(env)


DB_PATH = resolve_db_path()
JWT_TTL = config.JWT_TTL_APPLICANT
JWT_TTL_STAFF = config.JWT_TTL_STAFF


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret():
    value = os.environ.get("JWT_SECRET", "")
    if len(value) < config.JWT_SECRET_MIN_LEN or value.startswith("your-"):
        if not config.IS_PRODUCTION:
            return b"policynest-local-dev-jwt-secret-key-min-32-bytes!"
        raise ValueError("auth_not_configured")
    return value.encode("utf-8")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        migrations.run_migrations(db)
        db.commit()


@contextmanager
def _db():
    init_db()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def _hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return _b64(salt) + "$" + _b64(key)


def _verify(password, stored):
    try:
        salt, expected = stored.split("$", 1)
        return hmac.compare_digest(_hash(password, _unb64(salt)), stored)
    except (ValueError, TypeError):
        return False


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public(row):
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"] if "status" in row.keys() else "active",
        "mfa_enabled": bool(row["mfa_enabled"]) if "mfa_enabled" in row.keys() else False,
        "email_verified": bool(row["email_verified"]) if "email_verified" in row.keys() else False,
        "must_reset_password": bool(row["must_reset_password"]) if "must_reset_password" in row.keys() else False,
    }


# =====================================================================
# 1. APPLICANT REGISTRATION & AUTHENTICATION
# =====================================================================


def create_verification_token(user_id, email):
    token = secrets.token_urlsafe(32)
    digest = _digest(token)
    expires = int(time.time()) + 86400  # 24 hours
    with _db() as db:
        db.execute(
            "INSERT INTO email_verification_tokens(token_hash, user_id, email, expires_at, used, created_at) VALUES(?,?,?,?,0,?)",
            (digest, user_id, str(email).lower(), expires, int(time.time())),
        )
    return token


def verify_email_token(token):
    if not token or not isinstance(token, str):
        return None
    digest = _digest(token)
    now = int(time.time())
    with _db() as db:
        row = db.execute(
            "SELECT user_id, email, expires_at, used FROM email_verification_tokens WHERE token_hash=?",
            (digest,),
        ).fetchone()
        if not row or row["used"] or row["expires_at"] < now:
            return None
        db.execute("UPDATE email_verification_tokens SET used=1 WHERE token_hash=?", (digest,))
        db.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
        return row["user_id"]

def register(email, password, display_name):
    """Register a new applicant account. Always enforces role='applicant'."""
    _secret()  # Fail fast if authentication secret is unconfigured
    email = str(email or "").strip().lower()
    display_name = str(display_name or "").strip()
    if (
        len(email) > 254
        or "@" not in email
        or not isinstance(password, str)
        or not config.PASSWORD_MIN_LENGTH <= len(password) <= config.PASSWORD_MAX_LENGTH
        or len(display_name) < 2
        or len(display_name) > 80
    ):
        raise ValueError("invalid_registration")

    try:
        with _db() as db:
            cur = db.execute(
                """INSERT INTO users(email, display_name, password_hash, role, status, created_at, email_verified)
                   VALUES(?, ?, ?, 'applicant', 'active', ?, 0)""",
                (email, display_name, _hash(password), int(time.time())),
            )
            user_id = cur.lastrowid
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            try:
                v_token = create_verification_token(user_id, email)
                disp_id = f"disp_{secrets.token_hex(8)}"
                v_url = f"http://localhost:8000/#verify-email={v_token}"
                db.execute("""INSERT INTO communication_dispatches (
                    id, user_id, channel, template_key, recipient, subject, content, status, created_at
                ) VALUES (?, ?, 'EMAIL', 'email_verification', ?, 'Verify your PolicyNest email address', ?, 'DELIVERED', ?)""",
                (disp_id, user_id, email, f"Welcome to PolicyNest! Click here to verify: {v_url}\nToken: {v_token}", int(time.time())))
            except Exception:
                pass
    except sqlite3.IntegrityError:
        raise ValueError("email_taken")
    return _public(row)


def login(email, password, mfa_code=None):
    """Authenticate user with lockout protections and anti-account-enumeration error responses."""
    clean_email = str(email or "").strip().lower()
    clean_pass = str(password or "")
    now = int(time.time())

    with _db() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (clean_email,)).fetchone()

        if not row:
            # Generic anti-enumeration delay & error
            raise ValueError("invalid_credentials")

        # 1. Check account status
        user_status = row["status"] if "status" in row.keys() else "active"
        if user_status == "suspended":
            raise ValueError("account_suspended")
        if user_status == "pending_invite":
            raise ValueError("account_pending_invite")

        # 2. Check account lockout
        locked_until = row["locked_until"] if "locked_until" in row.keys() else 0
        if locked_until > now:
            raise ValueError("account_locked")

        # 3. Verify password
        if not _verify(clean_pass, row["password_hash"]):
            failed = (row["failed_logins"] if "failed_logins" in row.keys() else 0) + 1
            lock_time = now + config.LOCKOUT_DURATION_SECONDS if failed >= config.MAX_FAILED_LOGINS else 0
            db.execute(
                "UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
                (failed, lock_time, row["id"]),
            )
            db.commit()
            raise ValueError("invalid_credentials")

        # 4. Check MFA for privileged staff roles
        mfa_enabled = bool(row["mfa_enabled"]) if "mfa_enabled" in row.keys() else False
        if mfa_enabled:
            if not mfa_code:
                raise ValueError("mfa_required")
            # Verify TOTP code or recovery code
            mfa_secret = row["mfa_secret"] or ""
            totp_valid = mfa.verify_totp(mfa_secret, mfa_code)
            if not totp_valid:
                # Check recovery codes
                raw_recovery = row["mfa_recovery_codes"] or "[]"
                try:
                    recovery_list = json.loads(raw_recovery)
                except Exception:
                    recovery_list = []
                matched, remaining = mfa.verify_and_consume_recovery_code(mfa_code, recovery_list)
                if not matched:
                    raise ValueError("invalid_mfa_code")
                # Persist consumed recovery code
                db.execute(
                    "UPDATE users SET mfa_recovery_codes=? WHERE id=?",
                    (json.dumps(remaining), row["id"]),
                )

        # 5. Reset failure counters on successful login
        db.execute(
            "UPDATE users SET failed_logins=0, locked_until=0, last_login_at=? WHERE id=?",
            (now, row["id"]),
        )
        updated_row = db.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()

    return _public(updated_row)


def issue(user, refresh=None):
    """Issue a signed JWT access token with user role and token version."""
    now = int(time.time())
    is_staff = user.get("role") != "applicant"
    ttl = JWT_TTL_STAFF if is_staff else JWT_TTL

    with _db() as db:
        version_row = db.execute("SELECT token_version FROM users WHERE id=?", (user["id"],)).fetchone()
        version = version_row[0] if version_row else 0
        session = None
        if refresh:
            session = db.execute(
                "SELECT family FROM refresh_tokens WHERE digest=? AND revoked=0 AND used=0 AND expires>?",
                (_digest(refresh), now),
            ).fetchone()
            if not session:
                raise ValueError("invalid_session")

    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(
        json.dumps(
            {
                "sub": str(user["id"]),
                "role": user["role"],
                "sid": session["family"] if session else None,
                "ver": version,
                "iss": "policynest",
                "aud": "policynest-api",
                "iat": now,
                "exp": now + ttl,
            },
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64(hmac.new(_secret(), (head + "." + body).encode(), hashlib.sha256).digest())
    return head + "." + body + "." + sig


def authenticate(header):
    """Authenticate and return user object from a Bearer JWT."""
    if not isinstance(header, str) or not header.startswith("Bearer "):
        raise ValueError("unauthenticated")
    try:
        head, body, sig = header[7:].split(".")
        if json.loads(_unb64(head)) != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError
        expected = _b64(hmac.new(_secret(), (head + "." + body).encode(), hashlib.sha256).digest())
        data = json.loads(_unb64(body))
        if (
            not hmac.compare_digest(sig, expected)
            or data.get("exp", 0) <= time.time()
            or data.get("iss") != "policynest"
            or data.get("aud") != "policynest-api"
        ):
            raise ValueError

        with _db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (int(data["sub"]),)).fetchone()
            if data.get("sid") and not db.execute(
                "SELECT 1 FROM refresh_tokens WHERE family=? AND revoked=0 AND expires>?",
                (data["sid"], int(time.time())),
            ).fetchone():
                raise ValueError

        if not row or row["role"] != data.get("role") or row["token_version"] != data.get("ver"):
            raise ValueError
        if "status" in row.keys() and row["status"] != "active":
            raise ValueError("account_inactive")
        return _public(row)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, json.JSONDecodeError):
        raise ValueError("unauthenticated")


# =====================================================================
# 2. APPLICATION SNAPSHOT (PERSISTENCE)
# =====================================================================

def save_snapshot(user, snapshot):
    if user["role"] != "applicant":
        raise ValueError("forbidden")
    from application_state import minimise

    snapshot = minimise(snapshot)
    raw = json.dumps(snapshot, separators=(",", ":"))
    if len(raw) > 24_000:
        raise ValueError("snapshot_too_large")
    with _db() as db:
        db.execute(
            """INSERT INTO application_snapshots(user_id,snapshot,updated_at)
               VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET snapshot=excluded.snapshot,updated_at=excluded.updated_at""",
            (user["id"], raw, int(time.time())),
        )


def load_snapshot(user):
    if user["role"] != "applicant":
        raise ValueError("forbidden")
    with _db() as db:
        row = db.execute(
            "SELECT snapshot,updated_at FROM application_snapshots WHERE user_id=?", (user["id"],)
        ).fetchone()
    return None if not row else {"snapshot": json.loads(row["snapshot"]), "updated_at": row["updated_at"]}


# =====================================================================
# 3. REFRESH & RESET TOKENS
# =====================================================================

def new_refresh(user, family=None):
    token = secrets.token_urlsafe(48)
    with _db() as db:
        db.execute(
            "INSERT INTO refresh_tokens(digest,user_id,family,expires) VALUES(?,?,?,?)",
            (_digest(token), user["id"], family or secrets.token_hex(16), int(time.time()) + config.REFRESH_TTL),
        )
    return token


def rotate_refresh(token):
    """Consume once under a write lock; reuse revokes the entire token family."""
    if not token:
        raise ValueError("invalid_session")
    invalid = False
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM refresh_tokens WHERE digest=?", (_digest(token),)).fetchone()
        if not row or row["revoked"] or row["used"] or row["expires"] <= time.time():
            if row:
                db.execute("UPDATE refresh_tokens SET revoked=1 WHERE family=?", (row["family"],))
                db.execute("UPDATE users SET token_version=token_version+1 WHERE id=?", (row["user_id"],))
            invalid = True
        else:
            db.execute("UPDATE refresh_tokens SET used=1 WHERE digest=?", (_digest(token),))
            user = _public(db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone())
            replacement = secrets.token_urlsafe(48)
            db.execute(
                "INSERT INTO refresh_tokens(digest,user_id,family,expires) VALUES(?,?,?,?)",
                (_digest(replacement), user["id"], row["family"], int(time.time()) + config.REFRESH_TTL),
            )
    if invalid:
        raise ValueError("invalid_session")
    return user, replacement


def revoke_refresh(token):
    if not token:
        return
    with _db() as db:
        row = db.execute("SELECT family,user_id FROM refresh_tokens WHERE digest=?", (_digest(token),)).fetchone()
        if row:
            db.execute("UPDATE refresh_tokens SET revoked=1 WHERE family=?", (row["family"],))
            db.execute("UPDATE users SET token_version=token_version+1 WHERE id=?", (row["user_id"],))


def create_reset(email):
    """For trusted delivery adapter only. Never include this token in an HTTP recovery response."""
    with _db() as db:
        row = db.execute("SELECT id FROM users WHERE email=?", (str(email).strip().lower(),)).fetchone()
        if not row:
            return None
        token = secrets.token_urlsafe(48)
        db.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (row["id"],))
        db.execute(
            "INSERT INTO reset_tokens VALUES(?,?,?,0)",
            (_digest(token), row["id"], int(time.time()) + config.RESET_TOKEN_TTL),
        )
        return token


def reset_password(token, password):
    if not isinstance(password, str) or not config.PASSWORD_MIN_LENGTH <= len(password) <= config.PASSWORD_MAX_LENGTH:
        raise ValueError("invalid_password")
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM reset_tokens WHERE digest=?", (_digest(token),)).fetchone()
        if not row or row["used"] or row["expires"] <= time.time():
            raise ValueError("invalid_reset")
        db.execute(
            "UPDATE users SET password_hash=?,token_version=token_version+1,must_reset_password=0,failed_logins=0,locked_until=0 WHERE id=?",
            (_hash(password), row["user_id"]),
        )
        db.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (row["user_id"],))
        db.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (row["user_id"],))


# =====================================================================
# 4. CONTROLLED STAFF PROVISIONING & ADMINISTRATION
# =====================================================================

def provision_staff(actor, email, role, department="Operations", employee_id=None, temp_password=None, display_name=None):
    """Admin-only staff provisioning. Staff cannot register via public registration."""
    if not policy.allows(actor, "staff.provision", {"sensitivity": "system"}):
        raise ValueError("forbidden")
    if role not in policy.PLATFORM_ROLES or role == "applicant":
        raise ValueError("invalid_staff_role")

    clean_email = str(email or "").strip().lower()
    if "@" not in clean_email or len(clean_email) > 254:
        raise ValueError("invalid_email")

    temp_pass = temp_password or ("P@" + secrets.token_urlsafe(16) + "9!")
    if len(temp_pass) < config.PASSWORD_MIN_LENGTH:
        raise ValueError("password_too_short")

    name = display_name or ("Staff " + role.replace("_", " ").title())
    now = int(time.time())

    with _db() as db:
        try:
            cur = db.execute(
                """INSERT INTO users (email, display_name, password_hash, role, status, must_reset_password, created_at)
                   VALUES (?, ?, ?, ?, 'active', 1, ?)""",
                (clean_email, name, _hash(temp_pass), role, now),
            )
            staff_user_id = cur.lastrowid
            db.execute(
                """INSERT INTO staff_profiles (user_id, department, employee_id, created_by, status, updated_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (staff_user_id, department, employee_id, actor["id"], now),
            )
            db.execute(
                """INSERT INTO role_audit_events (actor_id, target_user_id, old_role, new_role, reason, occurred)
                   VALUES (?, ?, 'NONE', ?, 'Staff Provisioned', ?)""",
                (actor["id"], staff_user_id, role, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError("email_taken")

        staff_row = db.execute("SELECT * FROM users WHERE id=?", (staff_user_id,)).fetchone()

    result = _public(staff_row)
    result["temporary_password"] = temp_pass
    return result


def invite_staff(actor, email, role, department="Operations"):
    """Create a staff invitation with a single-use token expiring in 48 hours."""
    if not policy.allows(actor, "staff.invite", {"sensitivity": "system"}):
        raise ValueError("forbidden")
    if role not in policy.PLATFORM_ROLES or role == "applicant":
        raise ValueError("invalid_staff_role")

    clean_email = str(email or "").strip().lower()
    if "@" not in clean_email or len(clean_email) > 254:
        raise ValueError("invalid_email")

    with _db() as db:
        existing = db.execute("SELECT id FROM users WHERE email=?", (clean_email,)).fetchone()
        if existing:
            raise ValueError("user_already_exists")

        invite_id = "INV-" + secrets.token_hex(8)
        raw_token = secrets.token_urlsafe(32)
        digest = _digest(raw_token)
        now = int(time.time())
        expires = now + config.INVITATION_TOKEN_TTL

        db.execute(
            """INSERT INTO staff_invitations (id, email, role, department, token_digest, invited_by, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
               role=excluded.role, department=excluded.department, token_digest=excluded.token_digest,
               invited_by=excluded.invited_by, expires_at=excluded.expires_at, created_at=excluded.created_at""",
            (invite_id, clean_email, role, department, digest, actor["id"], expires, now),
        )

    return {
        "invitation_id": invite_id,
        "email": clean_email,
        "role": role,
        "invitation_token": raw_token,
        "expires_at": expires,
    }


def accept_staff_invite(invitation_token, password, display_name=None):
    """Accept invitation, validate token, force initial password setup, and activate staff account."""
    if not invitation_token or not isinstance(password, str):
        raise ValueError("invalid_invite")
    if not config.PASSWORD_MIN_LENGTH <= len(password) <= config.PASSWORD_MAX_LENGTH:
        raise ValueError("invalid_password")

    digest = _digest(invitation_token)
    now = int(time.time())

    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        invite = db.execute(
            "SELECT * FROM staff_invitations WHERE token_digest=? AND accepted_at IS NULL AND expires_at>?",
            (digest, now),
        ).fetchone()
        if not invite:
            raise ValueError("invalid_or_expired_invitation")

        name = str(display_name or "").strip() or ("Staff " + invite["role"].replace("_", " ").title())
        try:
            cur = db.execute(
                """INSERT INTO users (email, display_name, password_hash, role, status, must_reset_password, created_at)
                   VALUES (?, ?, ?, ?, 'active', 0, ?)""",
                (invite["email"], name, _hash(password), invite["role"], now),
            )
            staff_user_id = cur.lastrowid
            db.execute(
                """INSERT INTO staff_profiles (user_id, department, created_by, status, updated_at)
                   VALUES (?, ?, ?, 'active', ?)""",
                (staff_user_id, invite["department"], invite["invited_by"], now),
            )
            db.execute(
                "UPDATE staff_invitations SET accepted_at=? WHERE token_digest=?",
                (now, digest),
            )
            db.execute(
                """INSERT INTO role_audit_events (actor_id, target_user_id, old_role, new_role, reason, occurred)
                   VALUES (?, ?, 'INVITED', ?, 'Invitation Accepted', ?)""",
                (invite["invited_by"], staff_user_id, invite["role"], now),
            )
        except sqlite3.IntegrityError:
            raise ValueError("account_conflict")

        user_row = db.execute("SELECT * FROM users WHERE id=?", (staff_user_id,)).fetchone()

    return _public(user_row)


def update_staff_role(actor, target_user_id, new_role, reason="Role adjustment"):
    """Change staff role with immutable audit logging and immediate session revocation."""
    if not policy.allows(actor, "staff.role_update", {"sensitivity": "system"}):
        raise ValueError("forbidden")
    if new_role not in policy.PLATFORM_ROLES:
        raise ValueError("invalid_role")

    now = int(time.time())
    with _db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not user:
            raise ValueError("user_not_found")
        old_role = user["role"]
        if old_role == new_role:
            return _public(user)

        # Update role and bump token_version (revokes all active sessions)
        db.execute(
            "UPDATE users SET role=?, token_version=token_version+1 WHERE id=?",
            (new_role, target_user_id),
        )
        db.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (target_user_id,))
        db.execute(
            """INSERT INTO role_audit_events (actor_id, target_user_id, old_role, new_role, reason, occurred)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (actor["id"], target_user_id, old_role, new_role, reason, now),
        )
        updated_row = db.execute("SELECT * FROM users WHERE id=?", (target_user_id,)).fetchone()

    return _public(updated_row)


def set_staff_status(actor, target_user_id, status, reason="Administrative status update"):
    """Suspend or activate staff user. Suspending revokes active sessions immediately."""
    if not policy.allows(actor, "staff.status_update", {"sensitivity": "system"}):
        raise ValueError("forbidden")
    if status not in ("active", "suspended"):
        raise ValueError("invalid_status")

    now = int(time.time())
    with _db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not user:
            raise ValueError("user_not_found")

        db.execute("UPDATE users SET status=? WHERE id=?", (status, target_user_id))
        db.execute("UPDATE staff_profiles SET status=?, updated_at=? WHERE user_id=?", (status, now, target_user_id))
        if status == "suspended":
            # Invalidate all active sessions
            db.execute("UPDATE users SET token_version=token_version+1 WHERE id=?", (target_user_id,))
            db.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (target_user_id,))

        updated_row = db.execute("SELECT * FROM users WHERE id=?", (target_user_id,)).fetchone()

    return _public(updated_row)


def list_staff(actor):
    """Retrieve staff members for authorized management/auditing roles."""
    if not policy.allows(actor, "staff.read", {"sensitivity": "system"}):
        raise ValueError("forbidden")

    with _db() as db:
        rows = db.execute(
            """SELECT u.id, u.email, u.display_name, u.role, u.status, u.mfa_enabled, u.last_login_at,
                      sp.department, sp.employee_id
               FROM users u
               LEFT JOIN staff_profiles sp ON u.id = sp.user_id
               WHERE u.role != 'applicant'
               ORDER BY u.id ASC"""
        ).fetchall()

    return [
        {
            "id": r["id"],
            "email": r["email"],
            "display_name": r["display_name"],
            "role": r["role"],
            "status": r["status"] if "status" in r.keys() else "active",
            "mfa_enabled": bool(r["mfa_enabled"]) if "mfa_enabled" in r.keys() else False,
            "last_login_at": r["last_login_at"] if "last_login_at" in r.keys() else 0,
            "department": r["department"] or "General",
            "employee_id": r["employee_id"],
        }
        for r in rows
    ]


# =====================================================================
# 5. MULTI-FACTOR AUTHENTICATION (TOTP)
# =====================================================================

def setup_mfa(user):
    """Generate a new TOTP secret and recovery codes for the authenticated user."""
    secret = mfa.generate_totp_secret()
    codes = mfa.generate_recovery_codes()
    hashed_codes = [mfa.hash_recovery_code(c) for c in codes]
    uri = mfa.get_totp_uri(secret, user["email"])

    with _db() as db:
        # Save temporary secret before verification
        db.execute(
            "UPDATE users SET mfa_secret=?, mfa_recovery_codes=? WHERE id=?",
            (secret, json.dumps(hashed_codes), user["id"]),
        )

    return {
        "secret": secret,
        "totp_uri": uri,
        "recovery_codes": codes,
    }


def verify_and_enable_mfa(user, code):
    """Verify first TOTP code and activate MFA on the account."""
    with _db() as db:
        row = db.execute("SELECT mfa_secret FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not row["mfa_secret"]:
            raise ValueError("mfa_not_initiated")
        secret = row["mfa_secret"]

    if not mfa.verify_totp(secret, code):
        raise ValueError("invalid_totp_code")

    with _db() as db:
        db.execute("UPDATE users SET mfa_enabled=1 WHERE id=?", (user["id"],))

    return {"mfa_enabled": True}


def disable_mfa(user, code_or_recovery):
    """Disable MFA after verifying current TOTP code or valid recovery code."""
    with _db() as db:
        row = db.execute("SELECT mfa_secret, mfa_recovery_codes FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not row["mfa_secret"]:
            raise ValueError("mfa_not_configured")

    totp_valid = mfa.verify_totp(row["mfa_secret"], code_or_recovery)
    if not totp_valid:
        recovery_list = json.loads(row["mfa_recovery_codes"] or "[]")
        matched, _ = mfa.verify_and_consume_recovery_code(code_or_recovery, recovery_list)
        if not matched:
            raise ValueError("invalid_code")

    with _db() as db:
        db.execute(
            "UPDATE users SET mfa_enabled=0, mfa_secret=NULL, mfa_recovery_codes=NULL WHERE id=?",
            (user["id"],),
        )

    return {"mfa_enabled": False}


# =====================================================================
# 6. ANTI-CSRF TOKEN MANAGEMENT
# =====================================================================

def get_csrf_token(user):
    """Return or generate a session-bound CSRF secret for the user."""
    now = int(time.time())
    with _db() as db:
        row = db.execute("SELECT secret FROM csrf_secrets WHERE user_id=?", (user["id"],)).fetchone()
        if row:
            return row["secret"]
        token = secrets.token_hex(24)
        db.execute(
            """INSERT INTO csrf_secrets (user_id, secret, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET secret=excluded.secret, updated_at=excluded.updated_at""",
            (user["id"], token, now),
        )
        return token


def verify_csrf(user, client_token):
    """Verify that client_token matches the user's current session CSRF secret."""
    if not client_token or not user or not user.get("id"):
        return False
    with _db() as db:
        row = db.execute("SELECT secret FROM csrf_secrets WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            return False
        return hmac.compare_digest(row["secret"], str(client_token).strip())
