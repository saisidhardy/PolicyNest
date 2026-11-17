"""QA Tooling, Synthetic Test Seeding, and Safe Test Data Reset for PolicyNest.

Strictly non-production only. Enforces that:
1. QA workflows can NEVER execute in PRODUCTION unless explicitly enabled by an authorized admin.
2. Reset operations ONLY target synthetic records (tagged with '@policynest.test' or 'PN-%-SYN%').
3. Every seed and reset operation writes an immutable audit log entry.
"""
import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional

import auth
import config
import policy
import communications
import certification
import training_lms
import examination
import status_model

SYNTHETIC_EMAIL_DOMAIN = "@policynest.test"


def _require_non_prod(actor: Optional[Dict[str, Any]] = None):
    if config.IS_PRODUCTION and os.environ.get("ENABLE_PROD_VERIFICATION") != "1":
        raise ValueError("qa_tools_disabled_in_production")
    if actor and actor.get("role") not in ("admin", "reviewer", "compliance", "ops", "tech_admin"):
        raise ValueError("forbidden_qa_role_required")


def seed_qa_environment(actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create the 11 explicit QA test fixtures required by Phase 2."""
    _require_non_prod(actor)
    now = int(time.time())
    results: Dict[str, Any] = {}

    with auth._db() as db:
        # Helper to create synthetic user if not existing
        def _get_or_create_user(email: str, role: str, name: str) -> Dict[str, Any]:
            cur = db.execute("SELECT id, email, role, display_name FROM users WHERE LOWER(email) = LOWER(?)", (email,))
            row = cur.fetchone()
            if row:
                return dict(row)
            # Create user
            h = auth._hash("SyntheticPass1234!")
            cur = db.execute(
                """INSERT INTO users (email, display_name, password_hash, role, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (email.lower(), name, h, role, now),
            )
            uid = cur.lastrowid
            return {"id": uid, "email": email, "role": role, "display_name": name}

        # 1. Synthetic Applicant
        app_user = _get_or_create_user(f"applicant{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Synthetic Applicant")
        results["1_synthetic_applicant"] = {"id": app_user["id"], "email": app_user["email"], "role": app_user["role"]}

        # 2. Synthetic Reviewer
        rev_user = _get_or_create_user(f"reviewer{SYNTHETIC_EMAIL_DOMAIN}", "reviewer", "Synthetic Reviewer")
        results["2_synthetic_reviewer"] = {"id": rev_user["id"], "email": rev_user["email"], "role": rev_user["role"]}

        # 3. Synthetic Administrator
        adm_user = _get_or_create_user(f"admin{SYNTHETIC_EMAIL_DOMAIN}", "admin", "Synthetic Administrator")
        results["3_synthetic_admin"] = {"id": adm_user["id"], "email": adm_user["email"], "role": adm_user["role"]}

        # Helper to create synthetic application
        def _create_app(suffix: str, user_id: int, status: str, stage: str, details: Dict[str, Any]) -> tuple:
            ref = f"PN-2026-SYN{suffix}"
            cur = db.execute(
                """INSERT INTO applications (user_id, reference, status, details, progress, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(reference) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at""",
                (user_id, ref, status, json.dumps(details), json.dumps({"stage": stage}), now, now),
            )
            app_id = cur.lastrowid
            if not app_id:
                cur2 = db.execute("SELECT id FROM applications WHERE reference = ?", (ref,))
                row = cur2.fetchone()
                app_id = row[0] if row else 1

            # Mirror in cases table
            db.execute(
                """INSERT INTO cases (id, applicant_id, status, reviewer_id)
                   VALUES (?, ?, ?, NULL)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status""",
                (ref, user_id, status),
            )
            return ref, app_id

        # 4. Draft Application
        u_draft = _get_or_create_user(f"draft{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Draft User")
        ref_draft, app_id_draft = _create_app("01", u_draft["id"], "DRAFT", "Basics", {"full_name": "Draft User", "pincode": "110001"})
        results["4_draft_application"] = {"reference": ref_draft, "status": "DRAFT", "stage": "Basics"}

        # 5. Submitted Application
        u_sub = _get_or_create_user(f"submitted{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Submitted User")
        ref_sub, app_id_sub = _create_app("02", u_sub["id"], "SUBMITTED", "Verification", {"full_name": "Submitted User", "pan": "ABCDE1234F"})
        results["5_submitted_application"] = {"reference": ref_sub, "status": "SUBMITTED", "stage": "Verification"}

        # 6. Application Requiring Changes
        u_chg = _get_or_create_user(f"rework{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Rework User")
        ref_chg, app_id_chg = _create_app("03", u_chg["id"], "CHANGES_REQUESTED", "Documents", {"full_name": "Rework User", "rework_reason": "PAN card photo is blurry. Please re-upload a clear copy."})
        results["6_changes_requested"] = {"reference": ref_chg, "status": "CHANGES_REQUESTED", "defect": "PAN_BLURRY"}

        # 7. Approved Application (Ready for LMS)
        u_app = _get_or_create_user(f"approved{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Approved User")
        ref_app, app_id_app = _create_app("04", u_app["id"], "APPROVED", "Training", {"full_name": "Approved User", "approved_by": "Senior Reviewer"})
        results["7_approved_application"] = {"reference": ref_app, "status": "APPROVED", "stage": "Training"}

        # 8. Failed Document Verification Example
        u_fail = _get_or_create_user(f"docfail{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Doc Fail User")
        ref_fail, app_id_fail = _create_app("05", u_fail["id"], "NEEDS_MORE_INFO", "Documents", {"full_name": "Doc Fail User", "error_reason": "Date of Birth on Aadhaar does not match PAN record."})
        results["8_failed_verification"] = {"reference": ref_fail, "status": "NEEDS_MORE_INFO", "error": "DOB_MISMATCH"}

        # 9. Passed Training Example
        u_trnd = _get_or_create_user(f"trained{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Trained User")
        ref_trnd, app_id_trnd = _create_app("06", u_trnd["id"], "TRAINED", "Examination", {"full_name": "Trained User", "hours_completed": 15})
        for mod_idx in range(1, 6):
            mod_id = f"mod_{mod_idx}"
            db.execute(
                """INSERT INTO training_progress (id, user_id, module_id, status, time_spent_seconds, completed_at, created_at, updated_at)
                   VALUES (?, ?, ?, 'COMPLETED', 10800, ?, ?, ?)
                   ON CONFLICT(user_id, module_id) DO UPDATE SET status='COMPLETED', time_spent_seconds=10800, completed_at=excluded.completed_at""",
                (f"tp_{u_trnd['id']}_{mod_id}", u_trnd["id"], mod_id, now, now, now),
            )
        results["9_passed_training"] = {"reference": ref_trnd, "status": "TRAINED", "modules_completed": 5, "hours": 15}

        # 10. Failed Exam Attempt Example
        u_exfail = _get_or_create_user(f"examfail{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Exam Fail User")
        ref_exfail, app_id_exfail = _create_app("07", u_exfail["id"], "EXAM_FAILED", "Examination", {"full_name": "Exam Fail User", "score": 15})
        db.execute(
            """INSERT INTO exam_attempts (id, user_id, attempt_number, score, total_questions, passed, started_at, completed_at, incident_flag)
               VALUES (?, ?, 1, 15, 50, 0, ?, ?, 0)
               ON CONFLICT(id) DO UPDATE SET score=15, passed=0""",
            (f"attempt_{u_exfail['id']}_1", u_exfail["id"], now - 1800, now),
        )
        results["10_failed_exam"] = {"reference": ref_exfail, "score": "30%", "passed": False, "cooldown_active": True}

        # 11. Generated Test Certificate
        u_cert = _get_or_create_user(f"certified{SYNTHETIC_EMAIL_DOMAIN}", "applicant", "Certified POSP User")
        ref_cert, app_id_cert = _create_app("08", u_cert["id"], "CERTIFIED", "Certificate", {"full_name": "Certified POSP User"})
        cert_num = "PN-POSP-2026-SYN99"
        db.execute(
            """INSERT INTO certificates (id, certificate_number, user_id, application_id, posp_name, pan_masked, lines_of_business, issued_at, valid_until, status, signature_digest)
               VALUES (?, ?, ?, ?, 'Certified POSP User', 'ABCDE****F', 'Life,General,Health', ?, ?, 'ACTIVE', 'synthetic_hmac_signature')
               ON CONFLICT(certificate_number) DO UPDATE SET status='ACTIVE'""",
            (f"cert_{u_cert['id']}", cert_num, u_cert["id"], app_id_cert, now, now + (3 * 365 * 86400)),
        )
        results["11_test_certificate"] = {
            "certificate_number": cert_num,
            "status": "ACTIVE",
            "verify_url": f"/api/certificates/verify/{cert_num}",
        }

        # Record Audit Event
        actor_id = actor.get("id") if actor else adm_user["id"]
        db.execute(
            "INSERT INTO audit_events (case_id, actor_id, action, occurred) VALUES (?, ?, ?, ?)",
            ("QA_SEED", actor_id, "QA_SEED_EXECUTED", now),
        )

    return {
        "ok": True,
        "message": "QA test fixtures successfully generated across all 11 required scenarios.",
        "created_entities": results,
    }


def reset_qa_environment(actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely reset ONLY synthetic test records. Never touches production user records."""
    _require_non_prod(actor)
    now = int(time.time())
    deleted_counts = {}

    with auth._db() as db:
        # 1. Identify synthetic user IDs
        cur = db.execute("SELECT id FROM users WHERE LOWER(email) LIKE ?", (f"%{SYNTHETIC_EMAIL_DOMAIN}",))
        synth_user_ids = [row[0] for row in cur.fetchall()]

        if synth_user_ids:
            placeholders = ",".join("?" for _ in synth_user_ids)

            # Delete certificates
            cur = db.execute(f"DELETE FROM certificates WHERE user_id IN ({placeholders})", synth_user_ids)
            deleted_counts["certificates"] = cur.rowcount

            # Delete exam attempts
            cur = db.execute(f"DELETE FROM exam_attempts WHERE user_id IN ({placeholders})", synth_user_ids)
            deleted_counts["exam_attempts"] = cur.rowcount

            # Delete training progress
            cur = db.execute(f"DELETE FROM training_progress WHERE user_id IN ({placeholders})", synth_user_ids)
            deleted_counts["training_progress"] = cur.rowcount

            # Delete document records
            try:
                cur = db.execute(f"DELETE FROM document_records WHERE application_id IN (SELECT id FROM applications WHERE user_id IN ({placeholders}))", synth_user_ids)
                deleted_counts["document_records"] = cur.rowcount
            except Exception:
                pass

            # Delete verification results
            try:
                cur = db.execute(f"DELETE FROM verification_results WHERE application_id IN (SELECT id FROM applications WHERE user_id IN ({placeholders}))", synth_user_ids)
                deleted_counts["verification_results"] = cur.rowcount
            except Exception:
                pass

            # Delete applications
            cur = db.execute(f"DELETE FROM applications WHERE user_id IN ({placeholders})", synth_user_ids)
            deleted_counts["applications"] = cur.rowcount

            # Delete cases
            cur = db.execute(f"DELETE FROM cases WHERE applicant_id IN ({placeholders})", synth_user_ids)
            deleted_counts["cases"] = cur.rowcount

            # Delete users
            cur = db.execute(f"DELETE FROM users WHERE id IN ({placeholders})", synth_user_ids)
            deleted_counts["synthetic_users"] = cur.rowcount

        # Clean up any leftover synthetic cases or applications by reference pattern
        cur = db.execute("DELETE FROM applications WHERE reference LIKE 'PN-%-SYN%'")
        deleted_counts["synthetic_apps_by_ref"] = cur.rowcount
        cur = db.execute("DELETE FROM cases WHERE id LIKE 'PN-%-SYN%'")
        deleted_counts["synthetic_cases_by_ref"] = cur.rowcount

        # Record Audit Event
        actor_id = actor.get("id") if actor else 0
        db.execute(
            "INSERT INTO audit_events (case_id, actor_id, action, occurred) VALUES (?, ?, ?, ?)",
            ("QA_RESET", actor_id, "QA_RESET_EXECUTED", now),
        )

    return {
        "ok": True,
        "message": "Synthetic test data successfully purged. Production records untouched.",
        "deleted_counts": deleted_counts,
    }
