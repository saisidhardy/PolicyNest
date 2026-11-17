"""Forensic Document & Metadata Anomaly Detection, Risk Scoring, and AML Engine.

Provides:
1. Forensic document metadata & manipulation detection (Photoshop, Canva, GIMP, etc.).
2. Cross-applicant duplicate asset detection (reused file hashes, PANs, bank accounts).
3. Bank beneficiary mismatch anomaly scoring (mule / third-party account detection).
4. Device & IP network velocity tracking (onboarding syndicate detection).
5. Watchlist / Blacklist screening (fraud_blacklist).
6. Deterministic Composite Risk Scoring (0 - 100) and Automated Action Router:
   - Low Risk (0 - 30): Straight-through automated flow.
   - Medium Risk (31 - 70): Mandatory senior reviewer inspection / escalation.
   - High Risk (71 - 100): Automated risk_hold = 1, cases.status = 'FRAUD_HOLD', fraud_cases ticket.
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
from config import MANDATORY_DOCUMENT_SLOTS
from cross_checks import match_indian_names

log = logging.getLogger("policynest.fraud_engine")

# Known image editing and graphics manipulation software byte signatures
IMAGE_MANIPULATION_SIGNATURES = [
    (b"Adobe Photoshop", "Adobe Photoshop"),
    (b"Photoshop", "Adobe Photoshop"),
    (b"8BIM", "Adobe Photoshop IPTC/IRB"),
    (b"8BPS", "Adobe Photoshop Document"),
    (b"Canva", "Canva"),
    (b"canva", "Canva"),
    (b"GIMP", "GNU Image Manipulation Program (GIMP)"),
    (b"gimp", "GNU Image Manipulation Program (GIMP)"),
    (b"CorelDRAW", "CorelDRAW"),
    (b"Corel Paint", "Corel Paint"),
    (b"Paint.NET", "Paint.NET"),
]

# Risk rule definitions and calibrated weights
FRAUD_RULES = {
    "RULE_BLACKLIST_MATCH": {
        "rule_id": "RULE_BLACKLIST_MATCH",
        "name": "Entity on Fraud Blacklist",
        "points": 100,
        "severity": "HIGH",
        "description": "Identifier (PAN, bank account, document hash, or IP) matches active fraud blacklist.",
    },
    "RULE_DUPLICATE_PAN": {
        "rule_id": "RULE_DUPLICATE_PAN",
        "name": "Duplicate PAN Across Applicants",
        "points": 80,
        "severity": "HIGH",
        "description": "The submitted PAN is registered or claimed by another distinct applicant account.",
    },
    "RULE_DUPLICATE_BANK": {
        "rule_id": "RULE_DUPLICATE_BANK",
        "name": "Duplicate Bank Account Across Applicants",
        "points": 75,
        "severity": "HIGH",
        "description": "The bank account number or penny-drop digest is claimed by another distinct applicant.",
    },
    "RULE_REUSED_IMAGE_HASH": {
        "rule_id": "RULE_REUSED_IMAGE_HASH",
        "name": "Reused Document Image SHA-256",
        "points": 70,
        "severity": "HIGH",
        "description": "Exact same document image hash was previously uploaded by a different applicant.",
    },
    "RULE_UNDERAGE_ATTEMPT": {
        "rule_id": "RULE_UNDERAGE_ATTEMPT",
        "name": "Altered DOB After Underage Rejection",
        "points": 50,
        "severity": "HIGH",
        "description": "Applicant was previously rejected for age or DOB mismatch and re-applied with altered DOB.",
    },
    "RULE_BENEFICIARY_MISMATCH": {
        "rule_id": "RULE_BENEFICIARY_MISMATCH",
        "name": "Severe Bank Beneficiary Name Mismatch",
        "points": 45,
        "severity": "MEDIUM",
        "description": "Penny drop verified account holder name significantly diverges from applicant full name.",
    },
    "RULE_EDITING_SOFTWARE_DETECTED": {
        "rule_id": "RULE_EDITING_SOFTWARE_DETECTED",
        "name": "Image Editing Software Signatures Detected",
        "points": 40,
        "severity": "MEDIUM",
        "description": "Document bytes contain signatures of graphics manipulation software (Photoshop, Canva, GIMP).",
    },
    "RULE_HIGH_IP_VELOCITY": {
        "rule_id": "RULE_HIGH_IP_VELOCITY",
        "name": "High IP Address Onboarding Velocity",
        "points": 35,
        "severity": "MEDIUM",
        "description": "Three or more distinct applicants onboarded from the same IP address within a short window.",
    },
    "RULE_NAME_MISMATCH_PAN_AADHAAR": {
        "rule_id": "RULE_NAME_MISMATCH_PAN_AADHAAR",
        "name": "Severe PAN vs Aadhaar Name Mismatch",
        "points": 35,
        "severity": "MEDIUM",
        "description": "Cross-document name match between PAN and Aadhaar failed 8-tier verification.",
    },
    "RULE_QUALITY_DEFECT": {
        "rule_id": "RULE_QUALITY_DEFECT",
        "name": "Severe Document Quality Defects",
        "points": 15,
        "severity": "LOW",
        "description": "Uploaded document severely failed quality checks (excessive blur, glare, or darkness).",
    },
}


def inspect_image_bytes(file_bytes: bytes) -> Dict[str, Any]:
    """Inspect raw document bytes for known manipulation tools, headers, and metadata anomalies."""
    if not file_bytes:
        return {"editing_tool_detected": False, "tool_name": None, "signatures": []}

    detected_tools = []
    # Search in head (first 64KB) and tail (last 64KB) where EXIF and metadata blocks reside
    scan_chunk = file_bytes[:65536] + (file_bytes[-65536:] if len(file_bytes) > 65536 else b"")

    for sig, tool_name in IMAGE_MANIPULATION_SIGNATURES:
        if sig in scan_chunk:
            if tool_name not in detected_tools:
                detected_tools.append(tool_name)

    return {
        "editing_tool_detected": bool(detected_tools),
        "tool_name": detected_tools[0] if detected_tools else None,
        "signatures": detected_tools,
    }


def record_network_event(
    applicant_id: int,
    application_id: Optional[int],
    ip_address: str,
    user_agent: Optional[str] = None,
    event_type: str = "LOGIN",
) -> None:
    """Record an applicant device / network event for velocity and syndicate analysis."""
    if not ip_address:
        return
    # Strip port if present
    clean_ip = ip_address.split(":")[0].strip()
    now = int(time.time())
    with auth._db() as db:
        db.execute(
            """INSERT INTO applicant_network_events (
                applicant_id, application_id, ip_address, user_agent, event_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (applicant_id, application_id, clean_ip, (user_agent or "")[:250], event_type, now),
        )


def check_ip_velocity(applicant_id: int, ip_address: str, window_hours: int = 24) -> Dict[str, Any]:
    """Check if the IP address has seen >= 3 distinct applicants onboarded in the last window_hours."""
    if not ip_address or ip_address in ("127.0.0.1", "localhost", "::1"):
        return {"high_velocity": False, "count": 1, "distinct_applicants": [applicant_id]}

    clean_ip = ip_address.split(":")[0].strip()
    since = int(time.time()) - (window_hours * 3600)

    with auth._db() as db:
        rows = db.execute(
            """SELECT DISTINCT applicant_id FROM applicant_network_events
               WHERE ip_address=? AND created_at >= ?""",
            (clean_ip, since),
        ).fetchall()

    applicant_ids = [r[0] for r in rows]
    if applicant_id not in applicant_ids:
        applicant_ids.append(applicant_id)

    count = len(applicant_ids)
    return {
        "high_velocity": count >= 3,
        "count": count,
        "distinct_applicants": applicant_ids,
        "ip_address": clean_ip,
    }


def check_blacklist(
    pan_masked: Optional[str] = None,
    pan_raw: Optional[str] = None,
    bank_account: Optional[str] = None,
    file_hashes: Optional[List[str]] = None,
    ip_address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Screen identifiers against the active fraud blacklist."""
    hits = []
    with auth._db() as db:
        # Check PAN (masked or hash)
        if pan_masked:
            row = db.execute(
                "SELECT * FROM fraud_blacklist WHERE identifier_type='PAN' AND identifier_value=?",
                (pan_masked.strip().upper(),),
            ).fetchone()
            if row:
                hits.append(dict(row))
        if pan_raw:
            pan_hash = hashlib.sha256(pan_raw.strip().upper().encode("utf-8")).hexdigest()
            row = db.execute(
                "SELECT * FROM fraud_blacklist WHERE identifier_type='PAN_HASH' AND identifier_value=?",
                (pan_hash,),
            ).fetchone()
            if row:
                hits.append(dict(row))

        # Check Bank Account
        if bank_account:
            bank_hash = hashlib.sha256(bank_account.strip().encode("utf-8")).hexdigest()
            row = db.execute(
                "SELECT * FROM fraud_blacklist WHERE identifier_type='BANK_HASH' AND identifier_value=?",
                (bank_hash,),
            ).fetchone()
            if row:
                hits.append(dict(row))

        # Check File Hashes
        if file_hashes:
            for h in file_hashes:
                row = db.execute(
                    "SELECT * FROM fraud_blacklist WHERE identifier_type='IMAGE_HASH' AND identifier_value=?",
                    (h,),
                ).fetchone()
                if row:
                    hits.append(dict(row))

        # Check IP
        if ip_address and ip_address not in ("127.0.0.1", "localhost", "::1"):
            clean_ip = ip_address.split(":")[0].strip()
            row = db.execute(
                "SELECT * FROM fraud_blacklist WHERE identifier_type='IP_ADDRESS' AND identifier_value=?",
                (clean_ip,),
            ).fetchone()
            if row:
                hits.append(dict(row))

    return hits


def check_duplicate_document_hashes(application_id: int, user_id: int) -> List[Dict[str, Any]]:
    """Detect if any document uploaded in this application shares a SHA-256 hash with another user."""
    conflicts = []
    with auth._db() as db:
        # Get all documents for current application
        docs = db.execute(
            "SELECT slot, sha256_hash FROM document_records WHERE application_id=? AND sha256_hash IS NOT NULL",
            (application_id,),
        ).fetchall()

        for slot, sha256 in docs:
            # Check if any other user has uploaded this hash
            other = db.execute(
                """SELECT application_id, user_id, slot FROM document_records
                   WHERE sha256_hash=? AND user_id != ? LIMIT 5""",
                (sha256, user_id),
            ).fetchall()
            for other_app, other_user, other_slot in other:
                conflicts.append({
                    "slot": slot,
                    "sha256": sha256,
                    "conflict_application_id": other_app,
                    "conflict_user_id": other_user,
                    "conflict_slot": other_slot,
                })
    return conflicts


def check_duplicate_pan(applicant_id: int, application_id: int, pan_masked: str) -> Optional[Dict[str, Any]]:
    """Detect if the PAN was registered or verified by another applicant."""
    if not pan_masked:
        return None
    with auth._db() as db:
        # Check verification_results for PAN
        rows = db.execute(
            """SELECT application_id, response_digest FROM verification_results
               WHERE check_type='PAN' AND status='PASS' AND application_id != ?""",
            (application_id,),
        ).fetchall()
        for other_app_id, digest in rows:
            # Check if details matches or digest matches
            app_row = db.execute(
                "SELECT user_id, details FROM applications WHERE id=?",
                (other_app_id,),
            ).fetchone()
            if app_row:
                other_uid = app_row[0]
                if other_uid != applicant_id:
                    try:
                        other_details = json.loads(app_row[1] or "{}")
                        other_pan = (other_details.get("pan") or other_details.get("pan_masked") or "").strip().upper()
                        if other_pan and other_pan == pan_masked.strip().upper():
                            return {
                                "duplicate": True,
                                "conflict_application_id": other_app_id,
                                "conflict_user_id": other_uid,
                                "pan_masked": pan_masked,
                            }
                    except Exception:
                        pass
    return None


def check_duplicate_bank(applicant_id: int, application_id: int, bank_account_masked: str, ifsc: str) -> Optional[Dict[str, Any]]:
    """Detect if the same bank account + IFSC was claimed by another applicant."""
    if not bank_account_masked or not ifsc:
        return None
    with auth._db() as db:
        rows = db.execute(
            """SELECT id, user_id, details FROM applications WHERE id != ?""",
            (application_id,),
        ).fetchall()
        for other_app_id, other_uid, details_raw in rows:
            if other_uid != applicant_id:
                try:
                    dt = json.loads(details_raw or "{}")
                    other_acc = dt.get("bank_account") or dt.get("account_number") or ""
                    other_ifsc = (dt.get("ifsc") or "").strip().upper()
                    if other_ifsc == ifsc.strip().upper() and other_acc and other_acc == bank_account_masked:
                        return {
                            "duplicate": True,
                            "conflict_application_id": other_app_id,
                            "conflict_user_id": other_uid,
                            "bank_masked": bank_account_masked,
                        }
                except Exception:
                    pass
    return None


def evaluate_beneficiary_name_match(applicant_name: str, beneficiary_name: str) -> Dict[str, Any]:
    """Score similarity between applicant name and bank penny drop beneficiary name."""
    if not applicant_name or not beneficiary_name:
        return {"score": 1.0, "match": True, "tier": 0, "divergent": False}

    match_res = match_indian_names(applicant_name, beneficiary_name)
    score = match_res.get("score", 0.0)
    passed = match_res.get("matched", False)

    return {
        "score": score,
        "match": passed,
        "tier": match_res.get("tier"),
        "divergent": score < 0.60,
    }


def evaluate_application_risk(
    application_id_or_user: Any,
    client_ip: Optional[str] = None,
    client_user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Comprehensive, deterministic Risk & Fraud evaluation for an application.

    Calculates composite risk score (0-100), evaluates all rule conditions,
    populates evidence locker, and executes automatic state transitions for high-risk holds.
    """
    now = int(time.time())

    with auth._db() as db:
        # Resolve application
        if isinstance(application_id_or_user, int):
            app_row = db.execute("SELECT * FROM applications WHERE id=?", (application_id_or_user,)).fetchone()
        elif isinstance(application_id_or_user, dict) and "id" in application_id_or_user:
            app_row = db.execute(
                "SELECT * FROM applications WHERE user_id=? OR id=?",
                (application_id_or_user["id"], application_id_or_user["id"]),
            ).fetchone()
        else:
            raise ValueError("invalid_application_reference")

        if not app_row:
            raise FileNotFoundError("application_not_found")

        app_id = int(app_row["id"])
        user_id = int(app_row["user_id"])
        app_status = app_row["status"]
        app_details = json.loads(app_row["details"] or "{}")

        # 1. Collect Applicant Identifiers
        applicant_name = app_details.get("name") or ""
        pan_val = app_details.get("pan") or app_details.get("pan_masked") or ""
        bank_acc = app_details.get("bank_account") or app_details.get("account_number") or ""
        bank_ifsc = app_details.get("ifsc") or ""

        # 2. Collect Uploaded Documents
        doc_rows = db.execute(
            "SELECT slot, sha256_hash, mime_type, quality_score, rejection_reason FROM document_records WHERE application_id=?",
            (app_id,),
        ).fetchall()
        file_hashes = [r["sha256_hash"] for r in doc_rows if r["sha256_hash"]]

        # 3. Log network event if client_ip supplied
        if client_ip:
            record_network_event(user_id, app_id, client_ip, client_user_agent, "EVALUATE_RISK")

        # ---------------------------------------------------- Evaluate Rules
        triggered_rules = []
        evidence_locker = {}

        # Rule 1: Blacklist Screening
        blacklist_hits = check_blacklist(
            pan_masked=pan_val,
            bank_account=bank_acc,
            file_hashes=file_hashes,
            ip_address=client_ip,
        )
        if blacklist_hits:
            rule = FRAUD_RULES["RULE_BLACKLIST_MATCH"]
            triggered_rules.append(rule)
            evidence_locker["blacklist_matches"] = blacklist_hits

        # Rule 2: Duplicate PAN
        dup_pan = check_duplicate_pan(user_id, app_id, pan_val)
        if dup_pan:
            rule = FRAUD_RULES["RULE_DUPLICATE_PAN"]
            triggered_rules.append(rule)
            evidence_locker["duplicate_pan"] = dup_pan

        # Rule 3: Duplicate Bank Account
        dup_bank = check_duplicate_bank(user_id, app_id, bank_acc, bank_ifsc)
        if dup_bank:
            rule = FRAUD_RULES["RULE_DUPLICATE_BANK"]
            triggered_rules.append(rule)
            evidence_locker["duplicate_bank"] = dup_bank

        # Rule 4: Reused Document Image Hash
        dup_hashes = check_duplicate_document_hashes(app_id, user_id)
        if dup_hashes:
            rule = FRAUD_RULES["RULE_REUSED_IMAGE_HASH"]
            triggered_rules.append(rule)
            evidence_locker["reused_document_hashes"] = dup_hashes

        # Rule 5: Editing Software Signatures in Document Bytes
        detected_software = []
        for r in doc_rows:
            slot = r["slot"]
            # Look up storage path or inspect
            path_row = db.execute(
                "SELECT storage_path FROM document_records WHERE application_id=? AND slot=?",
                (app_id, slot),
            ).fetchone()
            if path_row and path_row[0]:
                try:
                    from storage import read_document_file
                    file_bytes = read_document_file(path_row[0])
                    sig_res = inspect_image_bytes(file_bytes)
                    if sig_res["editing_tool_detected"]:
                        detected_software.append({
                            "slot": slot,
                            "tool_name": sig_res["tool_name"],
                            "signatures": sig_res["signatures"],
                        })
                except Exception:
                    pass

        if detected_software:
            rule = FRAUD_RULES["RULE_EDITING_SOFTWARE_DETECTED"]
            triggered_rules.append(rule)
            evidence_locker["editing_software"] = detected_software

        # Rule 6: Bank Beneficiary Name Mismatch
        verif_bank = db.execute(
            "SELECT details_json FROM verification_results WHERE application_id=? AND check_type='BANK'",
            (app_id,),
        ).fetchone()
        if verif_bank and verif_bank[0]:
            try:
                b_details = json.loads(verif_bank[0])
                ben_name = b_details.get("beneficiary_name") or ""
                if ben_name and applicant_name:
                    ben_eval = evaluate_beneficiary_name_match(applicant_name, ben_name)
                    if ben_eval["divergent"]:
                        rule = FRAUD_RULES["RULE_BENEFICIARY_MISMATCH"]
                        triggered_rules.append(rule)
                        evidence_locker["beneficiary_mismatch"] = {
                            "applicant_name": applicant_name,
                            "beneficiary_name": ben_name,
                            "score": ben_eval["score"],
                            "tier": ben_eval["tier"],
                        }
            except Exception:
                pass

        # Rule 7: IP Address Velocity
        if client_ip:
            velocity_res = check_ip_velocity(user_id, client_ip)
            if velocity_res["high_velocity"]:
                rule = FRAUD_RULES["RULE_HIGH_IP_VELOCITY"]
                triggered_rules.append(rule)
                evidence_locker["ip_velocity"] = velocity_res

        # Rule 8: Underage Re-attempt check
        past_appeals = db.execute(
            """SELECT a.explanation, a.response FROM appeals a
               JOIN cases c ON a.case_id = c.id
               WHERE c.applicant_id=? AND (a.response LIKE '%underage%' OR a.response LIKE '%18%')""",
            (user_id,),
        ).fetchall()
        if past_appeals:
            rule = FRAUD_RULES["RULE_UNDERAGE_ATTEMPT"]
            triggered_rules.append(rule)
            evidence_locker["underage_reattempt"] = "Applicant previously had underage rejection citations."

        # Rule 9: Name Mismatch PAN vs Aadhaar from Cross Checks
        cross_chk = db.execute(
            """SELECT status, discrepancy_details FROM cross_document_checks
               WHERE application_id=? AND check_name='NAME_MATCH'""",
            (app_id,),
        ).fetchone()
        if cross_chk and cross_chk[0] == "FAIL":
            rule = FRAUD_RULES["RULE_NAME_MISMATCH_PAN_AADHAAR"]
            triggered_rules.append(rule)
            evidence_locker["name_mismatch_pan_aadhaar"] = cross_chk[1]

        # Rule 10: Quality Defects
        defect_count = sum(1 for r in doc_rows if (r["quality_score"] or 100) < 60)
        if defect_count >= 2:
            rule = FRAUD_RULES["RULE_QUALITY_DEFECT"]
            triggered_rules.append(rule)
            evidence_locker["quality_defects"] = f"{defect_count} documents with quality score < 60."

        # ---------------------------------------------------- Score Aggregation
        total_points = sum(r["points"] for r in triggered_rules)
        composite_score = min(100, total_points)

        if composite_score >= 71:
            risk_tier = "HIGH"
            hold_placed = 1
        elif composite_score >= 31:
            risk_tier = "MEDIUM"
            hold_placed = 0
        else:
            risk_tier = "LOW"
            hold_placed = 0

        # ---------------------------------------------------- Automated Router
        case_id = f"FC-{app_id}-{now}"
        triggered_rule_ids = [r["rule_id"] for r in triggered_rules]

        # Check existing fraud case
        existing_fc = db.execute(
            "SELECT id, status FROM fraud_cases WHERE application_id=?",
            (app_id,),
        ).fetchone()

        if existing_fc:
            fc_id = existing_fc[0]
            # Don't overwrite resolved cases if cleared, unless new high risk occurs
            curr_status = existing_fc[1]
            new_status = "FLAGGED" if curr_status in ("OPEN", "FLAGGED") else curr_status
            if risk_tier == "HIGH" and curr_status == "CLEARED_FALSE_POSITIVE":
                new_status = "FLAGGED"

            db.execute(
                """UPDATE fraud_cases
                   SET risk_score=?, risk_tier=?, signals_json=?, evidence_json=?,
                       hold_placed=?, updated_at=?, status=?
                   WHERE id=?""",
                (
                    composite_score,
                    risk_tier,
                    json.dumps(triggered_rule_ids),
                    json.dumps(evidence_locker),
                    hold_placed,
                    now,
                    new_status,
                    fc_id,
                ),
            )
        else:
            db.execute(
                """INSERT INTO fraud_cases (
                    id, application_id, applicant_id, status, anomaly_type,
                    signals_json, evidence_json, risk_score, risk_tier,
                    hold_placed, created_at, updated_at
                ) VALUES (?, ?, ?, 'FLAGGED', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id,
                    app_id,
                    user_id,
                    "AUTOMATED_RISK_EVALUATION",
                    json.dumps(triggered_rule_ids),
                    json.dumps(evidence_locker),
                    composite_score,
                    risk_tier,
                    hold_placed,
                    now,
                    now,
                ),
            )

        # Update application risk_hold and case state
        if risk_tier == "HIGH":
            db.execute("UPDATE applications SET risk_hold=1 WHERE id=?", (app_id,))
            # Update review case status to FRAUD_HOLD
            db.execute(
                "UPDATE cases SET status='FRAUD_HOLD', updated_at=? WHERE applicant_id=?",
                (now, user_id),
            )
            # Record audit event
            db.execute(
                """INSERT INTO audit_events (case_id, actor_id, action, occurred)
                   VALUES (?, ?, 'FRAUD_HOLD_PLACED', ?)""",
                (f"PN-{app_id}", 0, now),
            )
        elif risk_tier == "MEDIUM":
            # Escalate for senior reviewer oversight
            db.execute(
                """UPDATE cases
                   SET status=CASE WHEN status NOT IN ('FRAUD_HOLD', 'REJECTED') THEN 'ESCALATED' ELSE status END,
                       escalation_reason='MEDIUM_RISK_ANOMALY',
                       updated_at=?
                   WHERE applicant_id=?""",
                (now, user_id),
            )

        return {
            "application_id": app_id,
            "applicant_id": user_id,
            "risk_score": composite_score,
            "risk_tier": risk_tier,
            "hold_placed": bool(hold_placed),
            "triggered_rules": [
                {
                    "rule_id": r["rule_id"],
                    "name": r["name"],
                    "points": r["points"],
                    "severity": r["severity"],
                    "description": r["description"],
                }
                for r in triggered_rules
            ],
            "evidence": evidence_locker,
        }
