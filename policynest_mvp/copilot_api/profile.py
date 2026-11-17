"""Applicant Profile, Account Security, and DPDP/GDPR Privacy Services.

Features:
- Complete applicant profile retrieval and editing (city, state, pincode, notifications).
- Contact data minimization: mobile number masking and no raw identity numbers in profiles.
- Secure self-service password changes requiring current-password re-authentication.
- Invalidation of all concurrent active sessions via token-version rotation.
- Portability & Data Subject Export: structured JSON package of all applicant data.
- Auditable Right-to-be-Forgotten / Data Deletion requests.
"""
import json
import re
import secrets
import sqlite3
import time

import auth
import config
import policy


def _mask_mobile(m):
    digits = re.sub(r"\D", "", str(m or ""))
    return ("•" * 6 + digits[-4:]) if len(digits) >= 4 else None


def _clean_mobile(value):
    digits = re.sub(r"[\s\-]", "", str(value or ""))
    digits = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", digits)
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("invalid_mobile")
    return digits


def get_applicant_profile(user):
    """Retrieve applicant profile with data minimization."""
    with auth._db() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row:
            raise ValueError("user_not_found")

        active_sessions = db.execute(
            "SELECT COUNT(DISTINCT family) FROM refresh_tokens WHERE user_id=? AND revoked=0 AND used=0 AND expires>?",
            (user["id"], int(time.time())),
        ).fetchone()[0]

    keys = row.keys()
    notif_raw = row["notification_prefs"] if "notification_prefs" in keys and row["notification_prefs"] else "{}"
    try:
        notif_prefs = json.loads(notif_raw)
    except Exception:
        notif_prefs = {"email": True, "in_app": True, "sms": False}

    return {
        "id": int(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "mobile_masked": _mask_mobile(row["mobile"]) if "mobile" in keys else None,
        "language": row["language"] if "language" in keys else "en",
        "city": row["city"] if "city" in keys else None,
        "state": row["state"] if "state" in keys else None,
        "pincode": row["pincode"] if "pincode" in keys else None,
        "email_verified": False,
        "mobile_verified": bool(row["mobile"]) if "mobile" in keys and row["mobile"] else False,
        "analytics_consent": bool(row["analytics_consent"]) if "analytics_consent" in keys else False,
        "active_sessions_count": max(1, active_sessions),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"] if "last_login_at" in keys else 0,
        "notification_preferences": notif_prefs,
    }


def update_applicant_profile(user, body):
    """Safe editing of applicant profile attributes."""
    if not isinstance(body, dict):
        raise ValueError("invalid_request")

    sets, args = [], []

    if "display_name" in body:
        name = str(body["display_name"] or "").strip()
        if not 2 <= len(name) <= 80:
            raise ValueError("invalid_display_name")
        sets.append("display_name=?")
        args.append(name)

    if "mobile" in body:
        mob = body["mobile"]
        if mob in (None, ""):
            sets.append("mobile=NULL")
        else:
            sets.append("mobile=?")
            args.append(_clean_mobile(mob))

    if "language" in body:
        lang = str(body["language"] or "").strip().lower()
        if lang not in ("en", "hi"):
            raise ValueError("invalid_language")
        sets.append("language=?")
        args.append(lang)

    if "city" in body:
        city = str(body["city"] or "").strip() if body["city"] else None
        if city and len(city) > 60:
            raise ValueError("invalid_city")
        sets.append("city=?")
        args.append(city)

    if "state" in body:
        st = str(body["state"] or "").strip() if body["state"] else None
        if st and len(st) > 40:
            raise ValueError("invalid_state")
        sets.append("state=?")
        args.append(st)

    if "pincode" in body:
        pin = str(body["pincode"] or "").strip() if body["pincode"] else None
        if pin and not re.fullmatch(r"\d{6}", pin):
            raise ValueError("invalid_pincode")
        sets.append("pincode=?")
        args.append(pin)

    if "analytics_consent" in body:
        if not isinstance(body["analytics_consent"], bool):
            raise ValueError("invalid_consent")
        sets.append("analytics_consent=?")
        args.append(1 if body["analytics_consent"] else 0)

    if "notification_preferences" in body:
        prefs = body["notification_preferences"]
        if not isinstance(prefs, dict):
            raise ValueError("invalid_notification_preferences")
        clean_prefs = {
            "email": bool(prefs.get("email", True)),
            "in_app": bool(prefs.get("in_app", True)),
            "sms": bool(prefs.get("sms", False)),
        }
        sets.append("notification_prefs=?")
        args.append(json.dumps(clean_prefs, separators=(",", ":")))

    if sets:
        with auth._db() as db:
            db.execute("UPDATE users SET " + ",".join(sets) + " WHERE id=?", args + [user["id"]])

    return get_applicant_profile(user)


def change_applicant_password(user, current_password, new_password):
    """Change password requiring verification of existing credentials, then revoke other sessions."""
    if not isinstance(new_password, str) or not config.PASSWORD_MIN_LENGTH <= len(new_password) <= config.PASSWORD_MAX_LENGTH:
        raise ValueError("invalid_password_length")

    with auth._db() as db:
        row = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not auth._verify(str(current_password or ""), row["password_hash"]):
            raise ValueError("invalid_current_password")

        # Update hash and bump token_version (invalidating active JWTs across other devices)
        db.execute(
            "UPDATE users SET password_hash=?, token_version=token_version+1, must_reset_password=0 WHERE id=?",
            (auth._hash(new_password), user["id"]),
        )
        # Invalidate refresh token families
        db.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user["id"],))

    return {"ok": True, "message": "Password updated successfully. Other sessions have been signed out."}


def sign_out_all_sessions(user):
    """Invalidate all active sessions across all devices for this applicant."""
    with auth._db() as db:
        db.execute("UPDATE users SET token_version=token_version+1 WHERE id=?", (user["id"],))
        db.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user["id"],))
    return {"ok": True, "message": "All sessions signed out."}


def export_applicant_data(user):
    """Generate complete data portability export package under DPDP / GDPR guidelines."""
    with auth._db() as db:
        user_row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        app_row = db.execute("SELECT * FROM applications WHERE user_id=?", (user["id"],)).fetchone()
        timeline_rows = db.execute(
            "SELECT t, actor, key, stage, doc FROM timeline WHERE user_id=? ORDER BY t ASC", (user["id"],)
        ).fetchall()
        notif_rows = db.execute(
            "SELECT type, key, stage, doc, action, created_at, read FROM notifications WHERE user_id=? ORDER BY created_at ASC",
            (user["id"],),
        ).fetchall()

    export_pkg = {
        "export_metadata": {
            "platform": "PolicyNest POSP Onboarding",
            "exported_at": int(time.time()),
            "format_version": "1.0",
        },
        "user_profile": get_applicant_profile(user),
        "application": (
            {
                "reference": app_row["reference"],
                "status": app_row["status"],
                "stage": app_row["stage"] if "stage" in app_row.keys() else "Welcome",
                "details": json.loads(app_row["details"]),
                "progress": json.loads(app_row["progress"]),
                "created_at": app_row["created_at"],
                "updated_at": app_row["updated_at"],
            }
            if app_row
            else None
        ),
        "timeline_events": [dict(r) for r in timeline_rows],
        "notifications": [dict(r) for r in notif_rows],
    }
    return export_pkg


def request_account_deletion(user, reason=None):
    """Register an auditable deletion/erasure request."""
    req_id = "DEL-" + secrets.token_hex(8)
    now = int(time.time())
    with auth._db() as db:
        db.execute(
            """INSERT INTO data_deletion_requests (id, user_id, status, reason, requested_at)
               VALUES (?, ?, 'REQUESTED', ?, ?)""",
            (req_id, user["id"], str(reason or "")[:500], now),
        )
    return {
        "request_id": req_id,
        "status": "REQUESTED",
        "message": "Your account deletion request has been submitted for compliance verification.",
    }
