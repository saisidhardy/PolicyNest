"""Durable Server-Side Application Management, Autosave, and Dashboard Services.

Features:
- Non-derived human-readable application reference generator: PN-YYYY-XXXXX.
- Optimistic concurrency control via version checking to prevent stale overwrites across devices.
- Cross-device exact resume resolution (stage, section, subpage, document slot).
- Comprehensive applicant dashboard aggregator providing a unified first viewport view.
"""
import json
import secrets
import sqlite3
import time

import auth
import next_action
import policy
import portal
import status_model


def _new_reference():
    """Generate server-side human-readable reference ID: PN-YYYY-XXXXX."""
    year = time.gmtime().tm_year
    rand_seq = secrets.randbelow(90000) + 10000
    return f"PN-{year}-{rand_seq}"


def get_or_create_application(user):
    """Retrieve existing application for applicant or create a fresh draft with unique reference."""
    if user.get("role") != "applicant":
        raise ValueError("forbidden")

    portal.init()
    now = int(time.time())

    with auth._db() as db:
        row = db.execute("SELECT * FROM applications WHERE user_id=?", (user["id"],)).fetchone()
        if row:
            return format_application(row)

        # Retry loop to guarantee reference uniqueness
        for _ in range(20):
            ref = _new_reference()
            try:
                cur = db.execute(
                    """INSERT INTO applications(user_id, reference, version, status, stage, section, page,
                                               details, progress, resume_position, created_at, updated_at)
                       VALUES(?, ?, 1, 'DRAFT', 'Welcome', 'welcome', 1, '{}', '{}', '{}', ?, ?)""",
                    (user["id"], ref, now, now),
                )
                # Also ensure baseline case exists in cases table for reviewer workflows
                db.execute(
                    "INSERT OR IGNORE INTO cases(id, applicant_id, reviewer_id, status) VALUES(?, ?, NULL, 'DRAFT')",
                    (ref, user["id"]),
                )
                row = db.execute("SELECT * FROM applications WHERE id=?", (cur.lastrowid,)).fetchone()
                # Record timeline started event
                portal.record(db, user["id"], "application_started", stage="Welcome")
                return format_application(row)
            except sqlite3.IntegrityError:
                continue

        raise ValueError("reference_generation_failed")


def get_application(user):
    """Fetch application by authenticated applicant user."""
    if user.get("role") != "applicant":
        raise ValueError("forbidden")

    portal.init()
    with auth._db() as db:
        row = db.execute("SELECT * FROM applications WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise ValueError("no_application")
        return format_application(row)


def format_application(row):
    """Format raw SQLite row into clean application dictionary."""
    details = json.loads(row["details"] or "{}")
    if details.get("mobile"):
        details["mobile"] = portal._mask_mobile(details["mobile"])

    progress = json.loads(row["progress"] or "{}")
    keys = row.keys()

    resume_pos = json.loads(row["resume_position"] or "{}") if "resume_position" in keys else {}

    return {
        "id": row["id"],
        "reference": row["reference"],
        "version": row["version"],
        "status": row["status"],
        "stage": row["stage"] if "stage" in keys else progress.get("stage", "Welcome"),
        "section": row["section"] if "section" in keys else "basics",
        "page": row["page"] if "page" in keys else 1,
        "details": details,
        "progress": progress,
        "resume_position": resume_pos,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_draft(user, body):
    """Autosave draft with optimistic concurrency locking."""
    if user.get("role") != "applicant":
        raise ValueError("forbidden")

    client_version = body.get("version")
    if client_version is None or not isinstance(client_version, int):
        raise ValueError("version_required")

    portal.init()
    with auth._db() as db:
        row = db.execute("SELECT * FROM applications WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise ValueError("no_application")

        # Concurrency Check: Stale Version Detection
        if row["version"] != client_version:
            current_app = format_application(row)
            raise ValueError("conflict_detected")

        stored_details = json.loads(row["details"] or "{}")
        details = portal.clean_details(body["details"], stored_details) if "details" in body else stored_details

        stored_progress = json.loads(row["progress"] or "{}")
        progress = portal.clean_progress(body["progress"]) if "progress" in body else stored_progress

        resume_pos = body.get("resume_position")
        if resume_pos is not None and not isinstance(resume_pos, dict):
            resume_pos = {}
        resume_str = json.dumps(resume_pos or {}, separators=(",", ":"))

        stage = str(body.get("stage") or progress.get("stage") or (row["stage"] if "stage" in row.keys() else "Welcome"))[:30]
        section = str(body.get("section") or (row["section"] if "section" in row.keys() else "basics"))[:30]
        page = int(body.get("page") or (row["page"] if "page" in row.keys() else 1))

        # Check allowed status transition
        new_status = row["status"]
        if row["status"] in ("DRAFT", "IN_PROGRESS"):
            new_status = "IN_PROGRESS" if stage not in ("Welcome", "Before you start") else "DRAFT"

        now = int(time.time())
        new_version = client_version + 1

        db.execute(
            """UPDATE applications
               SET version=?, details=?, progress=?, resume_position=?, stage=?, section=?, page=?, status=?, updated_at=?
               WHERE user_id=? AND version=?""",
            (
                new_version,
                json.dumps(details, separators=(",", ":")),
                json.dumps(progress, separators=(",", ":")),
                resume_str,
                stage,
                section,
                page,
                new_status,
                now,
                user["id"],
                client_version,
            ),
        )

        # Mirror status in cases table
        db.execute("UPDATE cases SET status=? WHERE applicant_id=?", (new_status, user["id"]))

    return {
        "ok": True,
        "version": new_version,
        "updated_at": now,
        "status": new_status,
    }


def get_resume_position(user):
    """Retrieve exact resume position across devices."""
    app = get_application(user)
    resume = app.get("resume_position") or {}
    progress = app.get("progress") or {}

    stage = resume.get("stage") or app.get("stage") or "Welcome"
    section = resume.get("section") or app.get("section") or "basics"
    page = resume.get("page") or app.get("page") or 1
    doc_slot = resume.get("doc_slot") or ""

    return {
        "reference": app["reference"],
        "stage": stage,
        "section": section,
        "page": page,
        "doc_slot": doc_slot,
        "last_saved": app["updated_at"],
        "destination": f"#{section}" if section else f"#{stage.lower()}",
    }


def submit_application(user):
    """Validate completeness and transition draft application to SUBMITTED state."""
    app = get_application(user)
    current_status = app["status"]

    if current_status not in ("DRAFT", "IN_PROGRESS", "NEEDS_MORE_INFO"):
        raise ValueError("cannot_submit_in_current_state")

    details = app.get("details") or {}
    docs = app.get("progress", {}).get("documents") or {}

    # Basic validations
    if not (details.get("name") and details.get("dob") and details.get("state")):
        raise ValueError("incomplete_personal_details")

    # Document validations
    for slot in ("PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK"):
        slot_status = docs.get(slot, {}).get("status", "not uploaded")
        if slot_status in ("not uploaded", "missing"):
            raise ValueError(f"missing_required_document_{slot}")

    now = int(time.time())
    with auth._db() as db:
        db.execute(
            "UPDATE applications SET status='SUBMITTED', submitted_at=?, updated_at=?, version=version+1 WHERE user_id=?",
            (now, now, user["id"]),
        )
        db.execute("UPDATE cases SET status='SUBMITTED' WHERE applicant_id=?", (user["id"],))
        portal.record(db, user["id"], "application_started", stage="Documents")

    return {
        "ok": True,
        "status": "SUBMITTED",
        "submitted_at": now,
        "reference": app["reference"],
        "message": "Application submitted successfully for underwriting review.",
    }


def get_applicant_dashboard(user, lang="en"):
    """Compile comprehensive single-viewport dashboard payload for applicant."""
    app = get_or_create_application(user)
    status_info = status_model.get_status_info(app["status"], lang=lang)
    next_action_info = next_action.resolve_next_action(app, lang=lang)
    resume = get_resume_position(user)

    # Compile 6-Stage Progress
    # Journey: Welcome (1) -> Basics (2) -> Documents (3) -> Training (4) -> Exam (5) -> Certificate (6)
    stage_names = ["Welcome", "Basics", "Documents", "Training", "Exam", "Certificate"]
    stage_names_hi = ["स्वागत", "मूल विवरण", "दस्तावेज़", "प्रशिक्षण", "परीक्षा", "प्रमाणपत्र"]

    current_stage_idx = 0
    cur_st = app.get("stage", "Welcome")
    if cur_st in stage_names:
        current_stage_idx = stage_names.index(cur_st)
    elif app["status"] in ("KYC_APPROVED", "TRAINING_IN_PROGRESS"):
        current_stage_idx = 3
    elif app["status"] in ("TRAINING_COMPLETE", "EXAM_ELIGIBLE", "EXAM_FAILED"):
        current_stage_idx = 4
    elif app["status"] == "CERTIFIED":
        current_stage_idx = 5

    stages_tracker = []
    for idx, name in enumerate(stage_names):
        if idx < current_stage_idx:
            st = "completed"
        elif idx == current_stage_idx:
            st = "active"
        else:
            st = "locked"

        stages_tracker.append({
            "stage_number": idx + 1,
            "name": name if lang != "hi" else stage_names_hi[idx],
            "key": name,
            "status": st,
        })

    # Compile Document Checklist Status
    docs_progress = app.get("progress", {}).get("documents") or {}
    checklist = []
    doc_labels = {
        "PAN": ("PAN Card", "पैन कार्ड"),
        "AADHAAR_FRONT": ("Aadhaar Front (Masked)", "आधार सामने (मास्क्ड)"),
        "AADHAAR_BACK": ("Aadhaar Back", "आधार पीछे"),
        "CLASS10": ("Class 10 Marksheet", "कक्षा 10 की अंकतालिका"),
        "BANK": ("Cancelled Cheque / Passbook", "रद्द किया गया चेक / पासबुक"),
    }
    for slot, (lbl_en, lbl_hi) in doc_labels.items():
        doc_entry = docs_progress.get(slot) or {}
        st = doc_entry.get("status", "not uploaded")
        issues = doc_entry.get("issues", [])
        checklist.append({
            "slot": slot,
            "label": lbl_en if lang != "hi" else lbl_hi,
            "status": st,
            "has_issues": len(issues) > 0,
            "issues": issues,
        })

    # Fetch Notifications
    with auth._db() as db:
        notifs_rows = db.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 3", (user["id"],)
        ).fetchall()
        unread_count = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (user["id"],)
        ).fetchone()[0]

    recent_notifs = [
        {
            "id": r["id"],
            "type": r["type"],
            "key": r["key"],
            "read": bool(r["read"]),
            "created_at": r["created_at"],
            "reference": r["reference"],
            "stage": r["stage"],
        }
        for r in notifs_rows
    ]

    greeting_en = f"Welcome back, {user.get('display_name', 'Applicant')}!"
    greeting_hi = f"वापसी पर स्वागत है, {user.get('display_name', 'आवेदक')}!"

    return {
        "greeting": greeting_hi if lang == "hi" else greeting_en,
        "reference": app["reference"],
        "status": status_info,
        "six_stage_progress": stages_tracker,
        "primary_next_action": next_action_info,
        "resume_position": resume,
        "last_saved": app["updated_at"],
        "document_checklist": checklist,
        "notifications_unread": unread_count,
        "recent_notifications": recent_notifs,
        "application": app,
    }
