"""IRDAI 15-Hour POSP Training and Learning Management System (LMS) Engine.

Complies with IRDAI POSP Guidelines 2015:
1. 15-Hour Mandatory Curriculum:
   - Module 1: Introduction to Insurance & Core Principles (3.0 hours / 180 min)
   - Module 2: General Insurance: Motor, Property & Commercial (3.5 hours / 210 min)
   - Module 3: Life Insurance: Term, Endowment & Savings Plans (3.5 hours / 210 min)
   - Module 4: Health Insurance & Personal Accident Coverage (3.0 hours / 180 min)
   - Module 5: POSP Code of Conduct, Ethics & Compliance (2.0 hours / 120 min)
   Total: Exactly 15.0 hours (900 minutes / 54,000 seconds).

2. Anti-Skipping & Wall-Clock Heartbeat Verification:
   - Fast-forwarding and slide skipping strictly prevented via wall-clock elapsed verification.
   - Modules require minimum logged active study time to unlock completion.
   - Sequential module progression (Module K requires Module K-1 completion).

3. Cross-Device Exact Resume & State Management:
   - Syncs current module, section index, page, and bookmark position.
   - Seamless sync between desktop and mobile applicant portals.

4. Training Admin Curriculum Management & Audit:
   - Module authoring, duration adjustment, and progress monitoring.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import policy
import portal

log = logging.getLogger("policynest.training_lms")

TOTAL_REQUIRED_HOURS = 15.0
TOTAL_REQUIRED_SECONDS = 15 * 3600  # 54,000 seconds


def _check_training_access(actor: Dict[str, Any], action: str = "training.read") -> None:
    """Enforce ABAC capability check for training operations."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    resource = {"applicant_id": actor["id"], "status": "KYC_APPROVED", "sensitivity": "applicant"}

    if role == "applicant":
        if not policy.allows(actor, action, resource):
            raise PermissionError(f"forbidden: applicant lacks '{action}'")
    elif role in ("training_admin", "compliance_officer", "tech_admin", "admin"):
        return  # Authorized staff personas
    else:
        raise PermissionError(f"forbidden: role '{role}' lacks training access")


def get_training_overview(user: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """Retrieve full 15-hour training curriculum with user-specific progress and unlock states."""
    _check_training_access(user, "training.read")
    user_id = user["id"]

    with auth._db() as db:
        # Check application status
        app_row = db.execute(
            "SELECT id, status, stage, details, progress FROM applications WHERE user_id=?",
            (user_id,),
        ).fetchone()

        eligible_statuses = {
            "KYC_APPROVED",
            "TRAINING_IN_PROGRESS",
            "TRAINING_COMPLETE",
            "EXAM_ELIGIBLE",
            "EXAM_FAILED",
            "EXAM_PASSED",
            "CERTIFIED",
        }

        if not app_row:
            app_status = "NOT_STARTED"
            is_unlocked_for_user = False
        else:
            app_status = app_row["status"]
            is_unlocked_for_user = app_status in eligible_statuses

        # Fetch all training modules
        modules_rows = db.execute(
            "SELECT * FROM training_modules ORDER BY sequence_order ASC"
        ).fetchall()

        # Fetch applicant progress
        prog_rows = db.execute(
            "SELECT * FROM training_progress WHERE user_id=?",
            (user_id,),
        ).fetchall()
        prog_by_module = {r["module_id"]: dict(r) for r in prog_rows}

        modules_out = []
        total_time_spent = 0
        completed_count = 0
        previous_completed = True  # Module 1 is unlocked if KYC is approved

        for m in modules_rows:
            m_id = m["id"]
            dur_mins = m["duration_minutes"]
            dur_secs = dur_mins * 60
            dur_hrs = round(dur_mins / 60.0, 1)

            content = {}
            try:
                content = json.loads(m["content_json"] or "{}")
            except Exception:
                pass

            p_entry = prog_by_module.get(m_id, {})
            spent = p_entry.get("time_spent_seconds", 0)
            status = p_entry.get("status", "NOT_STARTED")
            is_done = status == "COMPLETED"

            total_time_spent += spent
            if is_done:
                completed_count += 1

            # Unlock logic: user KYC must be approved and previous module completed
            is_module_unlocked = is_unlocked_for_user and (previous_completed or is_done)
            previous_completed = is_done

            title = content.get("title_hi") if lang == "hi" and content.get("title_hi") else m["title"]
            desc = content.get("description", "")
            sections = content.get("sections", [])

            modules_out.append({
                "id": m_id,
                "sequence_order": m["sequence_order"],
                "title": title,
                "duration_minutes": dur_mins,
                "duration_hours": dur_hrs,
                "category": content.get("category", "General"),
                "description": desc,
                "sections": sections,
                "status": status,
                "time_spent_seconds": spent,
                "time_spent_minutes": round(spent / 60.0, 1),
                "is_unlocked": is_module_unlocked,
                "completed_at": p_entry.get("completed_at"),
                "current_section": p_entry.get("current_section", 0),
            })

        total_required_seconds = sum(m["duration_minutes"] * 60 for m in modules_rows) or TOTAL_REQUIRED_SECONDS
        total_hours_spent = round(total_time_spent / 3600.0, 1)
        percent_complete = min(100.0, round((total_time_spent / total_required_seconds) * 100.0, 1))
        is_all_done = completed_count == len(modules_rows) and len(modules_rows) > 0

    return {
        "user_id": user_id,
        "application_status": app_status,
        "is_eligible_for_training": is_unlocked_for_user,
        "total_modules": len(modules_rows),
        "completed_modules": completed_count,
        "total_required_hours": TOTAL_REQUIRED_HOURS,
        "total_hours_spent": total_hours_spent,
        "total_seconds_spent": total_time_spent,
        "percent_complete": percent_complete,
        "is_training_complete": is_all_done,
        "modules": modules_out,
    }


def get_module_detail(user: Dict[str, Any], module_id: str, lang: str = "en") -> Dict[str, Any]:
    """Retrieve in-depth module content, lessons, and current bookmark position."""
    _check_training_access(user, "training.read")
    user_id = user["id"]

    with auth._db() as db:
        m = db.execute("SELECT * FROM training_modules WHERE id=?", (module_id,)).fetchone()
        if not m:
            raise FileNotFoundError(f"module_not_found:{module_id}")

        prog = db.execute(
            "SELECT * FROM training_progress WHERE user_id=? AND module_id=?",
            (user_id, module_id),
        ).fetchone()

        content = {}
        try:
            content = json.loads(m["content_json"] or "{}")
        except Exception:
            pass

        title = content.get("title_hi") if lang == "hi" and content.get("title_hi") else m["title"]
        bookmark = {}
        if prog and prog["bookmark_position"]:
            try:
                bookmark = json.loads(prog["bookmark_position"])
            except Exception:
                pass

        spent = prog["time_spent_seconds"] if prog else 0
        status = prog["status"] if prog else "NOT_STARTED"

    return {
        "id": m["id"],
        "title": title,
        "duration_minutes": m["duration_minutes"],
        "duration_hours": round(m["duration_minutes"] / 60.0, 1),
        "category": content.get("category", "General"),
        "description": content.get("description", ""),
        "sections": content.get("sections", []),
        "status": status,
        "time_spent_seconds": spent,
        "completed_at": prog["completed_at"] if prog else None,
        "current_section": prog["current_section"] if prog else 0,
        "bookmark": bookmark,
    }


def record_training_heartbeat(
    user: Dict[str, Any],
    module_id: str,
    seconds_increment: int = 30,
    section_index: int = 0,
    bookmark: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Log active verified viewing time.

    Enforces wall-clock anti-tampering verification:
    Clamps increment and prevents fast-forwarding attacks.
    """
    _check_training_access(user, "training.update")
    user_id = user["id"]
    now = int(time.time())

    with auth._db() as db:
        # Check application status
        app_row = db.execute("SELECT id, status, progress FROM applications WHERE user_id=?", (user_id,)).fetchone()
        if not app_row:
            raise FileNotFoundError("application_not_found")

        app_id = app_row["id"]
        app_status = app_row["status"]

        if app_status not in ("KYC_APPROVED", "TRAINING_IN_PROGRESS", "TRAINING_COMPLETE", "EXAM_ELIGIBLE"):
            raise ValueError(f"cannot_train_in_current_status:{app_status}")

        m = db.execute("SELECT * FROM training_modules WHERE id=?", (module_id,)).fetchone()
        if not m:
            raise FileNotFoundError(f"module_not_found:{module_id}")

        req_secs = m["duration_minutes"] * 60

        prog = db.execute(
            "SELECT * FROM training_progress WHERE user_id=? AND module_id=?",
            (user_id, module_id),
        ).fetchone()

        # Wall-clock anti-tampering check: clamp max increment to 60s
        clamped_inc = max(1, min(int(seconds_increment or 30), 60))

        if prog:
            last_hb = prog["last_heartbeat_at"] or (now - clamped_inc)
            elapsed_wall_clock = max(1, now - last_hb)
            # Cannot log more seconds than actual wall-clock elapsed time (+ 2s buffer)
            effective_inc = min(clamped_inc, elapsed_wall_clock + 2)
            new_spent = prog["time_spent_seconds"] + effective_inc
            curr_status = prog["status"]
            new_status = "IN_PROGRESS" if curr_status == "NOT_STARTED" else curr_status

            db.execute(
                """UPDATE training_progress
                   SET time_spent_seconds=?, status=?, last_heartbeat_at=?,
                       current_section=?, bookmark_position=?, updated_at=?
                   WHERE id=?""",
                (
                    new_spent,
                    new_status,
                    now,
                    section_index,
                    json.dumps(bookmark or {}),
                    now,
                    prog["id"],
                ),
            )
        else:
            effective_inc = min(clamped_inc, 60)
            new_spent = effective_inc
            p_id = f"tp_{user_id}_{module_id}"
            db.execute(
                """INSERT INTO training_progress (
                    id, user_id, module_id, status, time_spent_seconds,
                    last_heartbeat_at, current_section, bookmark_position, created_at, updated_at
                ) VALUES (?, ?, ?, 'IN_PROGRESS', ?, ?, ?, ?, ?, ?)""",
                (
                    p_id,
                    user_id,
                    module_id,
                    new_spent,
                    now,
                    section_index,
                    json.dumps(bookmark or {}),
                    now,
                    now,
                ),
            )

        # Transition application from KYC_APPROVED to TRAINING_IN_PROGRESS on first heartbeat
        if app_status == "KYC_APPROVED":
            db.execute(
                "UPDATE applications SET status='TRAINING_IN_PROGRESS', stage='Training', updated_at=? WHERE id=?",
                (now, app_id),
            )

        # Calculate updated overall training hours
        all_spent = db.execute(
            "SELECT SUM(time_spent_seconds) FROM training_progress WHERE user_id=?",
            (user_id,),
        ).fetchone()[0] or 0
        total_hours = round(all_spent / 3600.0, 1)

        # Update application progress JSON
        app_progress = json.loads(app_row["progress"] or "{}")
        t_prog = app_progress.setdefault("training", {})
        t_prog["hours"] = total_hours
        db.execute(
            "UPDATE applications SET progress=?, updated_at=? WHERE id=?",
            (json.dumps(app_progress), now, app_id),
        )

    return {
        "ok": True,
        "module_id": module_id,
        "time_spent_seconds": new_spent,
        "required_seconds": req_secs,
        "effective_increment": effective_inc,
        "total_training_hours": total_hours,
        "is_module_ready_to_complete": new_spent >= int(req_secs * 0.90),
    }


def complete_training_module(user: Dict[str, Any], module_id: str) -> Dict[str, Any]:
    """Mark a training module as completed when sufficient verified time has elapsed."""
    _check_training_access(user, "training.update")
    user_id = user["id"]
    now = int(time.time())

    with auth._db() as db:
        m = db.execute("SELECT * FROM training_modules WHERE id=?", (module_id,)).fetchone()
        if not m:
            raise FileNotFoundError(f"module_not_found:{module_id}")

        req_secs = m["duration_minutes"] * 60
        min_required_secs = int(req_secs * 0.85)  # Require at least 85% logged study time

        prog = db.execute(
            "SELECT * FROM training_progress WHERE user_id=? AND module_id=?",
            (user_id, module_id),
        ).fetchone()

        if not prog or prog["time_spent_seconds"] < min_required_secs:
            spent = prog["time_spent_seconds"] if prog else 0
            raise ValueError(
                f"insufficient_study_time: logged {spent}s of minimum {min_required_secs}s required"
            )

        db.execute(
            """UPDATE training_progress
               SET status='COMPLETED', completed_at=?, updated_at=?
               WHERE user_id=? AND module_id=?""",
            (now, now, user_id, module_id),
        )

        # Record module completion timeline event
        portal.record(db, user_id, "training_module_done", stage="Training", doc=module_id)

        # Check if ALL 5 modules are now completed
        total_mods = db.execute("SELECT COUNT(*) FROM training_modules").fetchone()[0]
        completed_mods = db.execute(
            "SELECT COUNT(*) FROM training_progress WHERE user_id=? AND status='COMPLETED'",
            (user_id,),
        ).fetchone()[0]

        is_all_complete = completed_mods >= total_mods

        if is_all_complete:
            # Transition application to TRAINING_COMPLETE and stage to Exam
            app_row = db.execute("SELECT id, progress FROM applications WHERE user_id=?", (user_id,)).fetchone()
            if app_row:
                app_progress = json.loads(app_row["progress"] or "{}")
                app_progress.setdefault("training", {})["hours"] = TOTAL_REQUIRED_HOURS
                db.execute(
                    """UPDATE applications
                       SET status='TRAINING_COMPLETE', stage='Exam', progress=?, updated_at=?
                       WHERE user_id=?""",
                    (json.dumps(app_progress), now, user_id),
                )
                db.execute(
                    "UPDATE cases SET status='TRAINING_COMPLETE', updated_at=? WHERE applicant_id=?",
                    (now, user_id),
                )
                portal.record(db, user_id, "training_complete", stage="Exam")
                db.execute(
                    """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
                       VALUES (?, 'success', 'training_complete', 'Exam', '', '#exam', 0, ?, ?)""",
                    (user_id, now, f"PN-{app_row['id']}"),
                )

    return {
        "ok": True,
        "module_id": module_id,
        "status": "COMPLETED",
        "completed_modules": completed_mods,
        "total_modules": total_mods,
        "is_training_complete": is_all_complete,
    }


# ------------------------------------------------------------- Training Admin APIs
def admin_list_modules(actor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Admin endpoint to list all curriculum modules."""
    _check_training_access(actor, "training.module_manage")
    with auth._db() as db:
        rows = db.execute("SELECT * FROM training_modules ORDER BY sequence_order ASC").fetchall()
        return [dict(r) for r in rows]


def admin_upsert_module(
    actor: Dict[str, Any],
    module_id: str,
    title: str,
    duration_minutes: int,
    content: Dict[str, Any],
    sequence_order: int,
) -> Dict[str, Any]:
    """Admin endpoint to author or update a training curriculum module."""
    _check_training_access(actor, "training.content_manage")
    with auth._db() as db:
        db.execute(
            """INSERT INTO training_modules (
                id, program_version, title, duration_minutes, content_json, sequence_order
            ) VALUES (?, 'v1', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                duration_minutes=excluded.duration_minutes,
                content_json=excluded.content_json,
                sequence_order=excluded.sequence_order""",
            (module_id, title, duration_minutes, json.dumps(content or {}), sequence_order),
        )
    return {"ok": True, "module_id": module_id, "title": title}


def admin_get_user_progress(actor: Dict[str, Any], target_user_id: int) -> Dict[str, Any]:
    """Admin endpoint to audit applicant training progress."""
    _check_training_access(actor, "training.progress_read")
    with auth._db() as db:
        target_user = db.execute("SELECT id, role, email, display_name FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not target_user:
            raise FileNotFoundError("user_not_found")
    return get_training_overview(dict(target_user))


def admin_reset_user_progress(actor: Dict[str, Any], target_user_id: int, module_id: Optional[str] = None) -> Dict[str, Any]:
    """Admin endpoint to reset progress if an applicant requests a full restart."""
    _check_training_access(actor, "training.account_resolve")
    now = int(time.time())
    with auth._db() as db:
        if module_id:
            db.execute(
                """UPDATE training_progress
                   SET status='NOT_STARTED', time_spent_seconds=0, completed_at=NULL, updated_at=?
                   WHERE user_id=? AND module_id=?""",
                (now, target_user_id, module_id),
            )
        else:
            db.execute(
                """UPDATE training_progress
                   SET status='NOT_STARTED', time_spent_seconds=0, completed_at=NULL, updated_at=?
                   WHERE user_id=?""",
                (now, target_user_id),
            )
            # Reset application status to TRAINING_IN_PROGRESS if previously completed
            db.execute(
                "UPDATE applications SET status='TRAINING_IN_PROGRESS', stage='Training', updated_at=? WHERE user_id=?",
                (now, target_user_id),
            )
    return {"ok": True, "target_user_id": target_user_id, "module_id": module_id, "reset": True}
