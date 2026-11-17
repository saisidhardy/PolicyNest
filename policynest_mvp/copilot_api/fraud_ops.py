"""Fraud Investigator Case Management, Operational Workflows, and Blacklist Administration.

Implements NIST SP 800-162 ABAC for fraud_investigator and compliance_officer personas:
1. Multi-tier queue filtering (OPEN, UNDER_INVESTIGATION, CONFIRMED_FRAUD, CLEARED_FALSE_POSITIVE).
2. Deep forensic dossier aggregation (evidence locker, duplicate matches, network activity).
3. Investigator assignment and active case handling.
4. Structured Decision Engine (CONFIRMED_FRAUD vs CLEARED_FALSE_POSITIVE).
5. Watchlist / Blacklist administration.
6. Strict Anti-Accusation Invariant: Public/applicant-facing notifications never contain banned
   fraud words ('fraud', 'fake', 'forged', 'tampered', 'suspicious', 'blacklisted').
"""
import hashlib
import json
import logging
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import policy
from fraud_engine import FRAUD_RULES, evaluate_application_risk

log = logging.getLogger("policynest.fraud_ops")

# Banned terminology for applicant-facing communication (Anti-Accusation Invariant)
BANNED_WORDS_PATTERN = re.compile(
    r"\b(fraud\w*|fake|forged|forgery|tamper\w*|suspicious|blacklisted|syndicate)\b",
    re.I,
)

SAFE_REJECTION_REASON = (
    "Document verification requirements could not be completed at this time under regulatory onboarding criteria."
)


def _check_fraud_access(actor: Dict[str, Any], action: str = "fraud.case_read") -> None:
    """Enforce ABAC capability check for fraud operations."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    if role not in ("fraud_investigator", "compliance_officer", "tech_admin", "admin"):
        raise PermissionError(f"forbidden: role '{role}' lacks fraud access")

    resource = {"applicant_id": 0, "status": "FLAGGED", "sensitivity": "restricted_fraud"}
    if not policy.allows(actor, action, resource):
        raise PermissionError(f"forbidden: actor lacks capability '{action}'")


def sanitize_external_message(text: str) -> str:
    """Guarantee that external/applicant messages never leak internal fraud terminology."""
    if not text:
        return SAFE_REJECTION_REASON
    if BANNED_WORDS_PATTERN.search(text):
        return SAFE_REJECTION_REASON
    return text


def list_fraud_cases(
    actor: Dict[str, Any],
    status_filter: Optional[str] = None,
    risk_tier: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Retrieve fraud cases with queue filtering, SLA summaries, and risk metrics."""
    _check_fraud_access(actor, "fraud.case_read")

    query_parts = ["1=1"]
    args = []

    if status_filter:
        s_upper = status_filter.strip().upper()
        if s_upper in ("FLAGGED", "OPEN"):
            query_parts.append("fc.status IN ('FLAGGED', 'OPEN')")
        elif s_upper in ("UNDER_INVESTIGATION", "INVESTIGATING"):
            query_parts.append("fc.status='UNDER_INVESTIGATION'")
        elif s_upper in ("CONFIRMED_FRAUD", "CONFIRMED"):
            query_parts.append("fc.status='CONFIRMED_FRAUD'")
        elif s_upper in ("CLEARED_FALSE_POSITIVE", "CLEARED"):
            query_parts.append("fc.status='CLEARED_FALSE_POSITIVE'")
        elif s_upper != "ALL":
            query_parts.append("fc.status=?")
            args.append(s_upper)

    if risk_tier:
        query_parts.append("fc.risk_tier=?")
        args.append(risk_tier.strip().upper())

    where_clause = " AND ".join(query_parts)

    with auth._db() as db:
        # Summary counts
        counts = {
            "all": db.execute("SELECT COUNT(*) FROM fraud_cases").fetchone()[0],
            "open": db.execute("SELECT COUNT(*) FROM fraud_cases WHERE status IN ('FLAGGED', 'OPEN')").fetchone()[0],
            "investigating": db.execute("SELECT COUNT(*) FROM fraud_cases WHERE status='UNDER_INVESTIGATION'").fetchone()[0],
            "confirmed": db.execute("SELECT COUNT(*) FROM fraud_cases WHERE status='CONFIRMED_FRAUD'").fetchone()[0],
            "cleared": db.execute("SELECT COUNT(*) FROM fraud_cases WHERE status='CLEARED_FALSE_POSITIVE'").fetchone()[0],
            "high_risk": db.execute("SELECT COUNT(*) FROM fraud_cases WHERE risk_tier='HIGH'").fetchone()[0],
        }

        # Query cases
        sql = f"""
            SELECT fc.*, a.reference as application_reference, u.email as applicant_email,
                   u.display_name as applicant_name, inv.display_name as investigator_name
            FROM fraud_cases fc
            JOIN applications a ON fc.application_id = a.id
            JOIN users u ON fc.applicant_id = u.id
            LEFT JOIN users inv ON fc.investigator_id = inv.id
            WHERE {where_clause}
            ORDER BY fc.risk_score DESC, fc.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = db.execute(sql, args + [max(1, min(limit, 100)), max(0, offset)]).fetchall()

        cases = []
        for r in rows:
            signals = []
            try:
                signals = json.loads(r["signals_json"] or "[]")
            except Exception:
                pass

            cases.append({
                "id": r["id"],
                "application_id": r["application_id"],
                "application_reference": r["application_reference"],
                "applicant_id": r["applicant_id"],
                "applicant_name": r["applicant_name"],
                "applicant_email": r["applicant_email"],
                "status": r["status"],
                "risk_score": r["risk_score"] or 0,
                "risk_tier": r["risk_tier"] or "LOW",
                "triggered_rules": signals,
                "investigator_id": r["investigator_id"],
                "investigator_name": r["investigator_name"],
                "hold_placed": bool(r["hold_placed"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "resolved_at": r["resolved_at"],
            })

    return {
        "summary": counts,
        "cases": cases,
        "total": len(cases),
        "limit": limit,
        "offset": offset,
    }


def get_fraud_dossier(actor: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    """Compile comprehensive forensic dossier for fraud case."""
    _check_fraud_access(actor, "fraud.evidence_read")

    with auth._db() as db:
        fc = db.execute(
            """SELECT fc.*, a.reference as application_reference, a.details as app_details,
                      u.email as applicant_email, u.display_name as applicant_name,
                      u.mobile as applicant_mobile, u.city, u.state
               FROM fraud_cases fc
               JOIN applications a ON fc.application_id = a.id
               JOIN users u ON fc.applicant_id = u.id
               WHERE fc.id=? OR fc.application_id=?""",
            (case_id, case_id),
        ).fetchone()

        if not fc:
            raise FileNotFoundError(f"fraud_case_not_found:{case_id}")

        app_id = fc["application_id"]
        applicant_id = fc["applicant_id"]

        # Parse signals and evidence
        signals = []
        try:
            signals = json.loads(fc["signals_json"] or "[]")
        except Exception:
            pass

        evidence = {}
        try:
            evidence = json.loads(fc["evidence_json"] or "{}")
        except Exception:
            pass

        # Triggered rule details
        rule_details = []
        for s in signals:
            r_info = FRAUD_RULES.get(s)
            if r_info:
                rule_details.append(r_info)
            else:
                rule_details.append({
                    "rule_id": s,
                    "name": s,
                    "points": 30,
                    "severity": "MEDIUM",
                    "description": "Custom or manual signal.",
                })

        # Documents
        doc_rows = db.execute(
            """SELECT slot, mime_type, file_size, sha256_hash, status, quality_score, rejection_reason, created_at
               FROM document_records WHERE application_id=?""",
            (app_id,),
        ).fetchall()
        docs = [dict(d) for d in doc_rows]

        # Verification results
        verif_rows = db.execute(
            """SELECT check_type, status, match_score, details_json, created_at
               FROM verification_results WHERE application_id=?""",
            (app_id,),
        ).fetchall()
        verifications = []
        for v in verif_rows:
            v_dict = dict(v)
            try:
                v_dict["details"] = json.loads(v["details_json"] or "{}")
            except Exception:
                v_dict["details"] = {}
            verifications.append(v_dict)

        # Network velocity events
        net_rows = db.execute(
            """SELECT ip_address, user_agent, event_type, created_at
               FROM applicant_network_events WHERE applicant_id=?
               ORDER BY created_at DESC LIMIT 20""",
            (applicant_id,),
        ).fetchall()
        network_events = [dict(n) for n in net_rows]

        # Audit events
        audit_rows = db.execute(
            """SELECT action, occurred FROM audit_events
               WHERE case_id=? OR case_id=?
               ORDER BY occurred ASC""",
            (f"PN-{app_id}", f"case_{app_id}"),
        ).fetchall()
        audit_trail = [dict(a) for a in audit_rows]

    return {
        "fraud_case": {
            "id": fc["id"],
            "application_id": fc["application_id"],
            "application_reference": fc["application_reference"],
            "applicant_id": fc["applicant_id"],
            "applicant_name": fc["applicant_name"],
            "applicant_email": fc["applicant_email"],
            "applicant_mobile": fc["applicant_mobile"],
            "city": fc["city"],
            "state": fc["state"],
            "status": fc["status"],
            "anomaly_type": fc["anomaly_type"],
            "risk_score": fc["risk_score"] or 0,
            "risk_tier": fc["risk_tier"] or "LOW",
            "hold_placed": bool(fc["hold_placed"]),
            "investigator_id": fc["investigator_id"],
            "notes": fc["notes"],
            "resolution_notes": fc["resolution_notes"],
            "created_at": fc["created_at"],
            "updated_at": fc["updated_at"],
            "resolved_at": fc["resolved_at"],
        },
        "triggered_rules": rule_details,
        "evidence_locker": evidence,
        "documents": docs,
        "verifications": verifications,
        "network_events": network_events,
        "audit_trail": audit_trail,
    }


def assign_investigator(
    actor: Dict[str, Any],
    case_id: str,
    investigator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Assign or claim a fraud investigation ticket."""
    _check_fraud_access(actor, "fraud.hold_manage")

    target_investigator = investigator_id or actor["id"]
    now = int(time.time())

    with auth._db() as db:
        fc = db.execute("SELECT id, status FROM fraud_cases WHERE id=?", (case_id,)).fetchone()
        if not fc:
            raise FileNotFoundError(f"fraud_case_not_found:{case_id}")

        db.execute(
            """UPDATE fraud_cases
               SET investigator_id=?, status='UNDER_INVESTIGATION', updated_at=?
               WHERE id=?""",
            (target_investigator, now, case_id),
        )

        # Audit event
        db.execute(
            """INSERT INTO audit_events (case_id, actor_id, action, occurred)
               VALUES (?, ?, 'FRAUD_INVESTIGATION_ASSIGNED', ?)""",
            (case_id, actor["id"], now),
        )

    return {"ok": True, "case_id": case_id, "investigator_id": target_investigator, "status": "UNDER_INVESTIGATION"}


def decide_fraud_case(
    actor: Dict[str, Any],
    case_id: str,
    decision: str,
    notes: str,
    blacklist_identifiers: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Execute investigator decision on a fraud case.

    Decision must be either:
    - 'CONFIRMED_FRAUD': Rejects application, sets risk_hold = 1, blacklists identifiers,
      and communicates safe neutral non-punitive reason without banned words.
    - 'CLEARED_FALSE_POSITIVE': Clears risk_hold = 0, restores application to review queue,
      allowing normal onboarding to proceed.
    """
    _check_fraud_access(actor, "fraud.decide")

    decision_upper = (decision or "").strip().upper()
    if decision_upper not in ("CONFIRMED_FRAUD", "CLEARED_FALSE_POSITIVE"):
        raise ValueError("invalid_decision: must be CONFIRMED_FRAUD or CLEARED_FALSE_POSITIVE")

    notes_clean = (notes or "").strip()
    if len(notes_clean) < 10:
        raise ValueError("justification_notes_required_minimum_10_characters")

    now = int(time.time())

    with auth._db() as db:
        fc = db.execute(
            "SELECT id, application_id, applicant_id, evidence_json FROM fraud_cases WHERE id=?",
            (case_id,),
        ).fetchone()

        if not fc:
            raise FileNotFoundError(f"fraud_case_not_found:{case_id}")

        app_id = fc["application_id"]
        applicant_id = fc["applicant_id"]

        if decision_upper == "CONFIRMED_FRAUD":
            # 1. Update fraud case
            db.execute(
                """UPDATE fraud_cases
                   SET status='CONFIRMED_FRAUD', hold_placed=1, investigator_id=?,
                       resolution_notes=?, resolved_at=?, updated_at=?
                   WHERE id=?""",
                (actor["id"], notes_clean, now, now, case_id),
            )

            # 2. Reject application and place permanent risk hold
            db.execute(
                "UPDATE applications SET status='REJECTED', risk_hold=1 WHERE id=?",
                (app_id,),
            )
            db.execute(
                "UPDATE cases SET status='FRAUD_HOLD', updated_at=? WHERE applicant_id=?",
                (now, applicant_id),
            )

            # 3. Add identifiers to blacklist
            if blacklist_identifiers:
                for b_item in blacklist_identifiers:
                    ident_type = b_item.get("type", "UNKNOWN").strip().upper()
                    ident_val = b_item.get("value", "").strip()
                    if ident_val:
                        db.execute(
                            """INSERT INTO fraud_blacklist (
                                identifier_type, identifier_value, reason, source_case_id, created_at
                            ) VALUES (?, ?, ?, ?, ?)""",
                            (ident_type, ident_val, notes_clean, case_id, now),
                        )

            # 4. Immutable Audit Event
            db.execute(
                """INSERT INTO audit_events (case_id, actor_id, action, occurred)
                   VALUES (?, ?, 'FRAUD_CONFIRMED', ?)""",
                (f"PN-{app_id}", actor["id"], now),
            )

            # 5. Public / External Timeline Notice (Anti-Accusation Invariant)
            safe_msg = sanitize_external_message(SAFE_REJECTION_REASON)
            db.execute(
                """INSERT OR IGNORE INTO timeline(user_id, t, actor, key, stage, doc)
                   VALUES (?, ?, 'compliance', 'verification_unsuccessful', '', '')""",
                (applicant_id, now),
            )
            db.execute(
                """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
                   VALUES (?, 'adverse', 'verification_unsuccessful', '', '', '', 0, ?, ?)""",
                (applicant_id, now, f"PN-{app_id}"),
            )

            result_status = "CONFIRMED_FRAUD"

        else:  # CLEARED_FALSE_POSITIVE
            # 1. Update fraud case
            db.execute(
                """UPDATE fraud_cases
                   SET status='CLEARED_FALSE_POSITIVE', hold_placed=0, investigator_id=?,
                       resolution_notes=?, resolved_at=?, updated_at=?
                   WHERE id=?""",
                (actor["id"], notes_clean, now, now, case_id),
            )

            # 2. Release risk hold and restore application to review
            db.execute(
                "UPDATE applications SET risk_hold=0, status='UNDER_REVIEW' WHERE id=?",
                (app_id,),
            )
            db.execute(
                "UPDATE cases SET status='IN_REVIEW', updated_at=? WHERE applicant_id=?",
                (now, applicant_id),
            )

            # 3. Immutable Audit Event
            db.execute(
                """INSERT INTO audit_events (case_id, actor_id, action, occurred)
                   VALUES (?, ?, 'FRAUD_CLEARED', ?)""",
                (f"PN-{app_id}", actor["id"], now),
            )

            # 4. Applicant notification that review continues
            db.execute(
                """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
                   VALUES (?, 'info', 'review_resumed', '', '', '', 0, ?, ?)""",
                (applicant_id, now, f"PN-{app_id}"),
            )

            result_status = "CLEARED_FALSE_POSITIVE"

    return {
        "ok": True,
        "case_id": case_id,
        "application_id": app_id,
        "decision": result_status,
        "investigator_id": actor["id"],
        "resolved_at": now,
        "notes": notes_clean,
    }


def list_blacklist(
    actor: Dict[str, Any],
    identifier_type: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Query entries in fraud blacklist."""
    _check_fraud_access(actor, "fraud.blacklist_manage")

    query = "SELECT * FROM fraud_blacklist"
    args = []
    if identifier_type:
        query += " WHERE identifier_type=?"
        args.append(identifier_type.strip().upper())

    query += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(limit, 200)))

    with auth._db() as db:
        rows = db.execute(query, args).fetchall()
        return [dict(r) for r in rows]


def add_to_blacklist(
    actor: Dict[str, Any],
    identifier_type: str,
    identifier_value: str,
    reason: str,
    source_case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Manually add an identifier to the fraud blacklist."""
    _check_fraud_access(actor, "fraud.blacklist_manage")

    i_type = (identifier_type or "").strip().upper()
    i_val = (identifier_value or "").strip()
    i_reason = (reason or "").strip()

    if not i_type or not i_val or not i_reason:
        raise ValueError("identifier_type_value_and_reason_required")

    now = int(time.time())
    with auth._db() as db:
        cur = db.execute(
            """INSERT INTO fraud_blacklist (
                identifier_type, identifier_value, reason, source_case_id, created_at
            ) VALUES (?, ?, ?, ?, ?)""",
            (i_type, i_val, i_reason, source_case_id, now),
        )
        new_id = cur.lastrowid

    return {
        "id": new_id,
        "identifier_type": i_type,
        "identifier_value": i_val,
        "reason": i_reason,
        "created_at": now,
    }
