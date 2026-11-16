"""Review Operations, Case Assignment, Decision Engine, and Appeals for PolicyNest.

Implements Milestone 4 capabilities:
1. Multi-Queue Review Operations (my_queue, unassigned, escalated, rework, fraud).
2. Atomic Case Claiming, Locking, and Workload Rebalancing.
3. Structured Decision Engine (APPROVE, REQUEST_CHANGES, REJECT, ESCALATE, FLAG_FRAUD).
4. Comprehensive Dossier Aggregation for Staff Cockpit.
5. Formal Dispute & Appeals Lifecycle with Senior Reviewer / Compliance Authority.
6. Immutable Audit Trail and Safe External Notification Separation.
"""
import json
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import migrations
import policy
import portal

# Event mapping for external applicant notifications
REVIEW_EVENT_MAP = {
    "KYC_APPROVED": "review_approved",
    "NEEDS_MORE_INFO": "review_more_info",
    "REJECTED": "review_rejected",
    "IN_REVIEW": "review_in_progress",
    "HUMAN_REVIEW": "review_in_progress",
    "ESCALATED": "review_in_progress",
}


def _ensure_tables():
    portal.init()
    with auth._db() as db:
        migrations.run_migrations(db)


def _audit(db, case_id: str, actor: Dict[str, Any], action: str):
    """Record immutable audit event."""
    now = int(time.time())
    db.execute(
        "INSERT INTO audit_events (case_id, actor_id, action, occurred) VALUES (?, ?, ?, ?)",
        (case_id, actor["id"], action, now),
    )


def get_queues(
    actor: Dict[str, Any],
    queue_type: str = "my_queue",
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """Retrieve filtered review queue and category counts for staff cockpit."""
    _ensure_tables()
    role = actor.get("role", "applicant")

    allowed_roles = {
        "reviewer",
        "senior_reviewer",
        "operations",
        "compliance_officer",
        "fraud_investigator",
        "tech_admin",
        "auditor",
        "admin",
    }
    if role not in allowed_roles:
        raise PermissionError("forbidden")

    with auth._db() as db:
        # Base query joining cases, applications, and users
        base_sql = """
            FROM cases c
            JOIN applications a ON c.applicant_id = a.user_id
            JOIN users u ON c.applicant_id = u.id
            LEFT JOIN users r ON c.reviewer_id = r.id
            WHERE 1=1
        """
        params: List[Any] = []

        # Queue type filtering
        if queue_type == "my_queue":
            base_sql += " AND c.reviewer_id = ?"
            params.append(actor["id"])
        elif queue_type == "unassigned":
            base_sql += " AND c.reviewer_id IS NULL AND c.status IN ('SUBMITTED', 'IN_REVIEW')"
        elif queue_type == "escalated":
            base_sql += " AND c.status = 'ESCALATED'"
        elif queue_type == "rework":
            base_sql += " AND c.status IN ('NEEDS_MORE_INFO', 'IN_REVIEW')"
        elif queue_type == "fraud":
            base_sql += " AND (c.status = 'FRAUD_HOLD' OR a.risk_hold = 1)"
        elif queue_type == "all":
            pass

        if status_filter:
            base_sql += " AND c.status = ?"
            params.append(status_filter)

        if search:
            s_clean = f"%{search.strip()}%"
            base_sql += " AND (c.id LIKE ? OR a.reference LIKE ? OR u.email LIKE ? OR u.display_name LIKE ?)"
            params.extend([s_clean, s_clean, s_clean, s_clean])

        # Bucket summary counts
        counts = {
            "my_queue": db.execute(
                "SELECT COUNT(*) FROM cases WHERE reviewer_id=?", (actor["id"],)
            ).fetchone()[0],
            "unassigned": db.execute(
                "SELECT COUNT(*) FROM cases WHERE reviewer_id IS NULL AND status IN ('SUBMITTED', 'IN_REVIEW')"
            ).fetchone()[0],
            "escalated": db.execute(
                "SELECT COUNT(*) FROM cases WHERE status='ESCALATED'"
            ).fetchone()[0],
            "rework": db.execute(
                "SELECT COUNT(*) FROM cases WHERE status IN ('NEEDS_MORE_INFO', 'IN_REVIEW')"
            ).fetchone()[0],
            "fraud": db.execute(
                "SELECT COUNT(*) FROM cases WHERE status='FRAUD_HOLD'"
            ).fetchone()[0],
            "all": db.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        }

        # Count total matching query
        count_sql = f"SELECT COUNT(*) {base_sql}"
        total = db.execute(count_sql, tuple(params)).fetchone()[0]

        # Fetch paginated rows
        offset = max(0, (page - 1) * limit)
        fetch_sql = f"""
            SELECT c.id, a.reference, c.applicant_id, u.display_name, u.email,
                   u.mobile, c.status, a.stage, c.reviewer_id, r.display_name,
                   a.submitted_at, a.updated_at, c.claimed_at, c.escalation_reason
            {base_sql}
            ORDER BY a.updated_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = db.execute(fetch_sql, tuple(params)).fetchall()

    now = int(time.time())
    cases_list = []
    for r in rows:
        submitted_at = r[10] or r[11] or now
        age_hours = (now - submitted_at) / 3600.0
        sla_status = "ON_TRACK"
        if age_hours > 24:
            sla_status = "BREACHED"
        elif age_hours > 12:
            sla_status = "NEARING_BREACH"

        cases_list.append({
            "case_id": r[0],
            "reference": r[1] or r[0],
            "applicant_id": r[2],
            "applicant_name": r[3] or "Applicant",
            "email": r[4],
            "masked_mobile": portal._mask_mobile(r[5]) if r[5] else None,
            "status": r[6],
            "stage": r[7] or "Documents",
            "reviewer_id": r[8],
            "reviewer_name": r[9],
            "submitted_at": r[10],
            "updated_at": r[11],
            "claimed_at": r[12],
            "escalation_reason": r[13],
            "sla_status": sla_status,
            "turnaround_hours": round(age_hours, 1),
        })

    return {
        "ok": True,
        "queue_type": queue_type,
        "total": total,
        "page": page,
        "limit": limit,
        "counts": counts,
        "cases": cases_list,
    }


def claim_case(actor: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    """Reviewer self-assigns an unassigned case."""
    _ensure_tables()
    role = actor.get("role")
    if role not in ("reviewer", "senior_reviewer", "admin"):
        raise PermissionError("forbidden")

    now = int(time.time())
    with auth._db() as db:
        case = db.execute("SELECT id, reviewer_id, status FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")

        # Atomic claim: only if unassigned
        cur = db.execute(
            """UPDATE cases
               SET reviewer_id=?, claimed_at=?, updated_at=?
               WHERE id=? AND (reviewer_id IS NULL OR reviewer_id=?)""",
            (actor["id"], now, now, case_id, actor["id"]),
        )
        if cur.rowcount == 0:
            raise ValueError("case_already_claimed")

        db.execute(
            """INSERT INTO assignment_history (case_id, previous_reviewer, new_reviewer, actor_id, occurred)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, case["reviewer_id"], actor["id"], actor["id"], now),
        )
        _audit(db, case_id, actor, "CASE_CLAIMED")

    return {
        "ok": True,
        "case_id": case_id,
        "reviewer_id": actor["id"],
        "claimed_at": now,
        "message": "Case successfully claimed.",
    }


def release_case(actor: Dict[str, Any], case_id: str, reason: str = "Released by reviewer") -> Dict[str, Any]:
    """Release a claimed case back to the unassigned queue."""
    _ensure_tables()
    role = actor.get("role")
    now = int(time.time())

    with auth._db() as db:
        case = db.execute("SELECT id, reviewer_id, status FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")

        # Authorization: must be current assigned reviewer or senior/ops/admin
        is_assigned = case["reviewer_id"] == actor.get("id")
        can_reassign = role in ("senior_reviewer", "operations", "tech_admin", "admin")
        if not (is_assigned or can_reassign):
            raise PermissionError("forbidden")

        db.execute(
            "UPDATE cases SET reviewer_id=NULL, claimed_at=NULL, updated_at=? WHERE id=?",
            (now, case_id),
        )
        db.execute(
            """INSERT INTO assignment_history (case_id, previous_reviewer, new_reviewer, actor_id, occurred)
               VALUES (?, ?, 0, ?, ?)""",
            (case_id, case["reviewer_id"], actor["id"], now),
        )
        _audit(db, case_id, actor, "CASE_RELEASED")

    return {
        "ok": True,
        "case_id": case_id,
        "released": True,
        "message": "Case released back to unassigned queue.",
    }


def reassign_case(
    actor: Dict[str, Any],
    case_id: str,
    target_reviewer_id: int,
    reason: str = "Workload rebalancing",
) -> Dict[str, Any]:
    """Reassign case to another reviewer (requires assignment.update capability)."""
    _ensure_tables()
    role = actor.get("role")
    if role not in ("senior_reviewer", "operations", "tech_admin", "admin"):
        raise PermissionError("forbidden")

    now = int(time.time())
    with auth._db() as db:
        case = db.execute("SELECT id, reviewer_id, status FROM cases WHERE id=?", (case_id,)).fetchone()
        target = db.execute("SELECT id, display_name, role FROM users WHERE id=?", (target_reviewer_id,)).fetchone()
        if not case or not target:
            raise ValueError("not_found")
        if target["role"] not in ("reviewer", "senior_reviewer"):
            raise ValueError("invalid_target_reviewer")

        db.execute(
            "UPDATE cases SET reviewer_id=?, claimed_at=?, updated_at=? WHERE id=?",
            (target_reviewer_id, now, now, case_id),
        )
        db.execute(
            """INSERT INTO assignment_history (case_id, previous_reviewer, new_reviewer, actor_id, occurred)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, case["reviewer_id"], target_reviewer_id, actor["id"], now),
        )
        _audit(db, case_id, actor, f"REASSIGNED_TO:{target['id']}")

    return {
        "ok": True,
        "case_id": case_id,
        "new_reviewer_id": target_reviewer_id,
        "reviewer_name": target["display_name"],
        "message": f"Case reassigned to {target['display_name']}.",
    }


def get_case_dossier(actor: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    """Compile comprehensive case dossier for staff review cockpit."""
    _ensure_tables()
    with auth._db() as db:
        case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")

        case_res = dict(case)
        if not policy.allows(actor, "application.read", case_res):
            raise PermissionError("forbidden")

        applicant_id = case["applicant_id"]
        app = db.execute("SELECT * FROM applications WHERE user_id=?", (applicant_id,)).fetchone()
        user = db.execute("SELECT id, email, display_name, mobile, city, state, pincode FROM users WHERE id=?", (applicant_id,)).fetchone()

        # Documents
        docs = db.execute(
            """SELECT id, slot, doc_type, mime_type, file_size, status,
                      quality_score, rejection_reason, created_at, updated_at
               FROM document_records
               WHERE application_id=?
               ORDER BY created_at ASC""",
            (app["id"] if app else 0,),
        ).fetchall()

        # Verifications
        verifs = db.execute(
            """SELECT id, provider, check_type, status, reference_id,
                      match_score, response_digest, details_json, created_at
               FROM verification_results
               WHERE application_id=?
               ORDER BY created_at DESC""",
            (app["id"] if app else 0,),
        ).fetchall()

        # Cross checks
        cross = db.execute(
            """SELECT id, check_name, status, discrepancy_details, created_at
               FROM cross_document_checks
               WHERE application_id=?
               ORDER BY created_at DESC""",
            (app["id"] if app else 0,),
        ).fetchall()

        # Review notes
        notes = db.execute(
            """SELECT rn.id, rn.reviewer_id, u.display_name, rn.note, rn.created
               FROM review_notes rn
               JOIN users u ON rn.reviewer_id = u.id
               WHERE rn.case_id=?
               ORDER BY rn.created DESC""",
            (case_id,),
        ).fetchall()

        # Audit events
        audits = db.execute(
            """SELECT ae.id, ae.actor_id, u.display_name, ae.action, ae.occurred
               FROM audit_events ae
               JOIN users u ON ae.actor_id = u.id
               WHERE ae.case_id=?
               ORDER BY ae.occurred DESC""",
            (case_id,),
        ).fetchall()

        # Appeals
        appeals_rows = db.execute(
            """SELECT id, explanation, status, response, created, resolved, evidence
               FROM appeals
               WHERE case_id=?
               ORDER BY created DESC""",
            (case_id,),
        ).fetchall()

    dossier = {
        "case": dict(case),
        "application": {
            "reference": app["reference"] if app else case_id,
            "status": app["status"] if app else case["status"],
            "stage": app["stage"] if app else "Documents",
            "section": app["section"] if app else "basics",
            "submitted_at": app["submitted_at"] if app else None,
            "verified_at": app["verified_at"] if app else None,
            "risk_hold": app["risk_hold"] if app else 0,
            "details": json.loads(app["details"]) if (app and app["details"]) else {},
        },
        "applicant": {
            "id": user["id"],
            "display_name": user["display_name"],
            "email": user["email"],
            "masked_mobile": portal._mask_mobile(user["mobile"]) if user["mobile"] else None,
            "city": user["city"],
            "state": user["state"],
            "pincode": user["pincode"],
        },
        "documents": [
            {
                "id": d[0],
                "slot": d[1],
                "doc_type": d[2],
                "mime_type": d[3],
                "file_size": d[4],
                "status": d[5],
                "quality_score": d[6],
                "rejection_reason": d[7],
                "created_at": d[8],
                "updated_at": d[9],
            }
            for d in docs
        ],
        "verifications": [
            {
                "id": v[0],
                "provider": v[1],
                "check_type": v[2],
                "status": v[3],
                "reference_id": v[4],
                "match_score": v[5],
                "response_digest": v[6],
                "details": json.loads(v[7]) if v[7] else {},
                "created_at": v[8],
            }
            for v in verifs
        ],
        "cross_checks": [
            {
                "id": c[0],
                "check_name": c[1],
                "status": c[2],
                "details": c[3],
                "created_at": c[4],
            }
            for c in cross
        ],
        "notes": [
            {
                "id": n[0],
                "reviewer_id": n[1],
                "reviewer_name": n[2],
                "note": n[3],
                "created_at": n[4],
            }
            for n in notes
        ],
        "audit_events": [
            {
                "id": a[0],
                "actor_id": a[1],
                "actor_name": a[2],
                "action": a[3],
                "occurred_at": a[4],
            }
            for a in audits
        ],
        "appeals": [
            {
                "id": ap[0],
                "explanation": ap[1],
                "status": ap[2],
                "response": ap[3],
                "created_at": ap[4],
                "resolved_at": ap[5],
            }
            for ap in appeals_rows
        ],
    }

    return dossier


def decide_case(
    actor: Dict[str, Any],
    case_id: str,
    status: str,
    note: str,
    rule: str,
    slot_defects: Optional[Dict[str, str]] = None,
    cooling_off_days: Optional[int] = 30,
) -> Dict[str, Any]:
    """Execute a structured underwriting decision on an application."""
    _ensure_tables()

    allowed_decisions = {
        "KYC_APPROVED",
        "NEEDS_MORE_INFO",
        "REJECTED",
        "ESCALATED",
        "FRAUD_HOLD",
        "HUMAN_REVIEW",
    }
    status_upper = (status or "").strip().upper()
    if status_upper not in allowed_decisions:
        raise ValueError("invalid_decision_status")

    if not isinstance(note, str) or not 10 <= len(note) <= 1500:
        raise ValueError("invalid_review_note")
    if not isinstance(rule, str) or not re.fullmatch(r"§[0-9.]+", rule):
        raise ValueError("invalid_rule_citation")

    now = int(time.time())

    with auth._db() as db:
        case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")

        case_res = dict(case)
        if not policy.allows(actor, "review.decide", case_res):
            raise PermissionError("forbidden")

        applicant_id = case["applicant_id"]
        app = db.execute("SELECT id, status FROM applications WHERE user_id=?", (applicant_id,)).fetchone()
        app_id = app["id"] if app else None

        cooling_off_until = None
        if status_upper == "REJECTED":
            cooling_off_until = now + (cooling_off_days or 30) * 86400

        # Update case
        db.execute(
            """UPDATE cases
               SET status=?, cooling_off_until=?, updated_at=?
               WHERE id=?""",
            (status_upper, cooling_off_until, now, case_id),
        )

        # Update application status
        if app_id:
            risk_flag = 1 if status_upper == "FRAUD_HOLD" else 0
            db.execute(
                "UPDATE applications SET status=?, risk_hold=?, updated_at=? WHERE id=?",
                (status_upper, risk_flag, now, app_id),
            )

        # Handle defective slots if changes requested
        if status_upper == "NEEDS_MORE_INFO" and slot_defects and app_id:
            for slot, reason in slot_defects.items():
                db.execute(
                    """UPDATE document_records
                       SET status='REUPLOAD_NEEDED', rejection_reason=?, updated_at=?
                       WHERE application_id=? AND slot=?""",
                    (reason, now, app_id, slot.upper()),
                )

        # Handle fraud flag ticket creation
        if status_upper == "FRAUD_HOLD" and app_id:
            db.execute(
                """INSERT OR REPLACE INTO fraud_cases (
                    id, application_id, applicant_id, status, anomaly_type,
                    notes, investigator_id, hold_placed, created_at
                ) VALUES (?, ?, ?, 'FLAGGED', 'REVIEWER_FRAUD_FLAG', ?, ?, 1, ?)""",
                (f"fc_{secrets.token_hex(8)}", app_id, applicant_id, note, actor["id"], now),
            )

        # Internal operational note (never shown directly to applicant)
        db.execute(
            "INSERT INTO review_notes (case_id, reviewer_id, note, created) VALUES (?, ?, ?, ?)",
            (case_id, actor["id"], f"{rule} {note}", now),
        )

        # Audit event
        _audit(db, case_id, actor, f"REVIEW_{status_upper}")

        # Send safe timeline notification if mapped
        event_key = REVIEW_EVENT_MAP.get(status_upper)
        if event_key:
            portal.record_reviewer_event(db, applicant_id, event_key)

    return {
        "ok": True,
        "case_id": case_id,
        "status": status_upper,
        "rule": rule,
        "decided_at": now,
        "cooling_off_until": cooling_off_until,
        "message": f"Application decided: {status_upper}",
    }


def submit_appeal(
    applicant_user: Dict[str, Any],
    case_id: str,
    explanation: str,
    evidence: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Applicant submits formal appeal against adverse decision or hold."""
    _ensure_tables()
    applicant_id = applicant_user.get("id")

    if not isinstance(explanation, str) or not 10 <= len(explanation) <= 1500:
        raise ValueError("invalid_explanation_length")

    # Anti-leak check: no raw identity numbers
    if re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b|\b[A-Za-z]{5}\d{4}[A-Za-z]\b|\b\d{9,18}\b", explanation):
        raise ValueError("do_not_include_identity_numbers")

    now = int(time.time())
    with auth._db() as db:
        case = db.execute("SELECT id, applicant_id, status FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")
        if case["applicant_id"] != applicant_id:
            raise PermissionError("forbidden")

        ref_id = "AP-" + secrets.token_hex(8).upper()
        ev_str = json.dumps(evidence or {})

        db.execute(
            """INSERT INTO appeals (id, case_id, explanation, status, created, evidence)
               VALUES (?, ?, ?, 'OPEN', ?, ?)""",
            (ref_id, case_id, explanation, now, ev_str),
        )

        # Update case and application status to APPEAL_SUBMITTED
        db.execute("UPDATE cases SET status='APPEAL_SUBMITTED', updated_at=? WHERE id=?", (now, case_id))
        db.execute("UPDATE applications SET status='APPEAL_SUBMITTED', updated_at=? WHERE user_id=?", (now, applicant_id))

        _audit(db, case_id, applicant_user, "APPEAL_SUBMITTED")
        portal.record(db, applicant_id, "dispute_submitted", stage="Documents", doc=ref_id)

    return {
        "ok": True,
        "appeal_reference": ref_id,
        "case_id": case_id,
        "status": "OPEN",
        "created_at": now,
        "message": "Appeal submitted successfully for Senior Review.",
    }


def list_appeals(actor: Dict[str, Any], status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """List appeals for Senior Reviewer, Compliance Officer, and Operations."""
    _ensure_tables()
    role = actor.get("role")
    if role not in ("senior_reviewer", "compliance_officer", "operations", "tech_admin", "admin"):
        raise PermissionError("forbidden")

    with auth._db() as db:
        sql = """
            SELECT ap.id, ap.case_id, c.applicant_id, u.display_name, u.email,
                   ap.explanation, ap.status, ap.response, ap.created, ap.resolved,
                   ap.resolved_by, c.status
            FROM appeals ap
            JOIN cases c ON ap.case_id = c.id
            JOIN users u ON c.applicant_id = u.id
            WHERE 1=1
        """
        params = []
        if status_filter:
            sql += " AND ap.status=?"
            params.append(status_filter)
        sql += " ORDER BY ap.created DESC"
        rows = db.execute(sql, tuple(params)).fetchall()

    return [
        {
            "appeal_id": r[0],
            "case_id": r[1],
            "applicant_id": r[2],
            "applicant_name": r[3],
            "email": r[4],
            "explanation": r[5],
            "status": r[6],
            "response": r[7],
            "created_at": r[8],
            "resolved_at": r[9],
            "resolved_by": r[10],
            "case_status": r[11],
        }
        for r in rows
    ]


def decide_appeal(
    actor: Dict[str, Any],
    appeal_reference: str,
    verdict: str,
    response_text: str,
    restore_status: Optional[str] = "KYC_APPROVED",
) -> Dict[str, Any]:
    """Senior Reviewer or Compliance Officer resolves an applicant appeal."""
    _ensure_tables()
    role = actor.get("role")

    # Invariant: Normal reviewer CANNOT decide appeals; must be senior_reviewer or compliance_officer
    if role not in ("senior_reviewer", "compliance_officer", "admin"):
        raise PermissionError("forbidden_only_senior_authority_can_resolve_appeals")

    verdict_upper = (verdict or "").strip().upper()
    if verdict_upper not in ("UPHELD", "OVERTURNED", "MORE_INFO"):
        raise ValueError("invalid_appeal_verdict")

    if not isinstance(response_text, str) or not 10 <= len(response_text) <= 1500:
        raise ValueError("invalid_response_text")

    # Safe public response sanitization (no fraud words or identity numbers)
    if re.search(r"\b(fraud\w*|fake|forged|tamper\w*|suspicious)\b|\b\d{4}\s?\d{4}\s?\d{4}\b|\b[A-Za-z]{5}\d{4}[A-Za-z]\b|\b\d{9,18}\b", response_text, re.I):
        raise ValueError("unsafe_public_response")

    now = int(time.time())
    with auth._db() as db:
        appeal = db.execute("SELECT * FROM appeals WHERE id=?", (appeal_reference,)).fetchone()
        if not appeal:
            raise FileNotFoundError("appeal_not_found")
        if appeal["status"] in ("UPHELD", "OVERTURNED", "RESOLVED"):
            raise ValueError("already_resolved")

        case = db.execute("SELECT * FROM cases WHERE id=?", (appeal["case_id"],)).fetchone()
        if not case:
            raise FileNotFoundError("case_not_found")

        # Resolve appeal
        db.execute(
            """UPDATE appeals
               SET status=?, response=?, resolved=?, resolved_by=?
               WHERE id=?""",
            (verdict_upper, response_text, now, actor["id"], appeal_reference),
        )

        # Update case and application status based on verdict
        new_case_status = case["status"]
        if verdict_upper == "OVERTURNED":
            new_case_status = restore_status or "KYC_APPROVED"
        elif verdict_upper == "UPHELD":
            new_case_status = "REJECTED"
        elif verdict_upper == "MORE_INFO":
            new_case_status = "NEEDS_MORE_INFO"

        db.execute(
            "UPDATE cases SET status=?, updated_at=? WHERE id=?",
            (new_case_status, now, appeal["case_id"]),
        )
        db.execute(
            "UPDATE applications SET status=?, updated_at=? WHERE user_id=?",
            (new_case_status, now, case["applicant_id"]),
        )

        _audit(db, appeal["case_id"], actor, f"APPEAL_{verdict_upper}")
        portal.record_reviewer_event(db, case["applicant_id"], "appeal_update")

    return {
        "ok": True,
        "appeal_reference": appeal_reference,
        "verdict": verdict_upper,
        "case_status": new_case_status,
        "resolved_at": now,
        "message": f"Appeal resolved: {verdict_upper}",
    }
