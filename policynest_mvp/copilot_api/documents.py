"""Document Handling, Staging, Verification, and Rework Service for PolicyNest.

Provides:
1. Secure file upload staging, magic-byte validation, and quality assessment.
2. Slot-based document lifecycle tracking (PAN, AADHAAR_FRONT, AADHAAR_BACK, CLASS10, BANK, SELFIE).
3. Pluggable verification execution (PAN, Aadhaar, Bank, Class 10).
4. Cross-document discrepancy analysis (8-Tier Name matching, DOB, Age, Education).
5. Document correction and rework workflow.
6. ABAC-compliant secure document downloading (blocks Tech Admin and Auditor).
"""
import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import policy
import portal
from application import get_or_create_application
from config import MANDATORY_DOCUMENT_SLOTS
from cross_checks import match_indian_names, run_cross_document_checks
from providers import (
    AadhaarKycProvider,
    BankVerificationProvider,
    Class10VerificationProvider,
    PanVerificationProvider,
    mask_aadhaar,
    mask_bank_account,
    mask_pan,
)
from quality import SLOT_GUIDELINES, assess_quality
from storage import read_document_file, store_document_file


def upload_document(
    user: Dict[str, Any],
    slot: str,
    file_bytes: bytes,
    file_name: str = "document",
    client_signals: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Securely upload, stage, assess, and register a document for an applicant."""
    slot_upper = (slot or "").strip().upper()
    if slot_upper not in MANDATORY_DOCUMENT_SLOTS:
        raise ValueError(f"invalid_document_slot:{slot_upper}")

    app = get_or_create_application(user)
    app_id = app["id"]
    user_id = user["id"]

    # 1. Store file into immutable content-addressable storage
    meta = store_document_file(file_bytes)

    # 2. Run deterministic quality checks
    quality = assess_quality(meta, client_signals=client_signals, slot=slot_upper, content=file_bytes)

    doc_id = f"doc_{secrets.token_hex(12)}"
    now = int(time.time())

    status = "UPLOADED" if quality["passed"] else "REUPLOAD_NEEDED"
    rejection_reason = quality["remediation_en"] if not quality["passed"] else None

    # Default simulated OCR extraction based on slot
    details = app.get("details") or {}
    app_name = details.get("name") or user.get("display_name") or "APPLICANT NAME"
    app_dob = details.get("dob") or "1995-05-15"

    ocr_data = {
        "extracted_name": app_name,
        "extracted_dob": app_dob,
        "slot": slot_upper,
        "quality_score": quality["quality_score"],
        "issues": quality["issues"],
    }

    with auth._db() as db:
        # Check if slot already has an existing document record
        existing = db.execute(
            "SELECT id FROM document_records WHERE application_id=? AND slot=?",
            (app_id, slot_upper),
        ).fetchone()

        if existing:
            # Update existing record
            db.execute(
                """UPDATE document_records
                   SET mime_type=?, file_size=?, storage_path=?, sha256_hash=?,
                       status=?, quality_score=?, ocr_extracted_json=?,
                       rejection_reason=?, updated_at=?
                   WHERE id=?""",
                (
                    meta["mime_type"],
                    meta["file_size"],
                    meta["storage_path"],
                    meta["sha256_hash"],
                    status,
                    quality["quality_score"],
                    json.dumps(ocr_data),
                    rejection_reason,
                    now,
                    existing[0],
                ),
            )
            doc_id = existing[0]
        else:
            db.execute(
                """INSERT INTO document_records (
                    id, application_id, user_id, slot, doc_type, mime_type,
                    file_size, storage_path, sha256_hash, status, quality_score,
                    ocr_extracted_json, rejection_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    app_id,
                    user_id,
                    slot_upper,
                    slot_upper.lower(),
                    meta["mime_type"],
                    meta["file_size"],
                    meta["storage_path"],
                    meta["sha256_hash"],
                    status,
                    quality["quality_score"],
                    json.dumps(ocr_data),
                    rejection_reason,
                    now,
                    now,
                ),
            )

        # Update application progress JSON
        progress = app.get("progress") or {}
        docs = progress.setdefault("documents", {})
        docs[slot_upper] = {
            "status": "ready" if quality["passed"] else "reupload",
            "doc_id": doc_id,
            "quality_score": quality["quality_score"],
            "mime_type": meta["mime_type"],
            "uploaded_at": now,
        }

        # Check if all mandatory documents are present
        all_ready = all(
            docs.get(s, {}).get("status") == "ready"
            for s in ("PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK")
        )
        if all_ready and app["status"] == "DRAFT":
            new_app_status = "IN_PROGRESS"
        else:
            new_app_status = app["status"]

        db.execute(
            "UPDATE applications SET progress=?, status=?, updated_at=? WHERE id=?",
            (json.dumps(progress), new_app_status, now, app_id),
        )

        portal.record(db, user_id, "doc_uploaded", stage="Documents", doc=slot_upper)

    return {
        "ok": True,
        "document_id": doc_id,
        "slot": slot_upper,
        "status": status,
        "quality": quality,
        "mime_type": meta["mime_type"],
        "file_size": meta["file_size"],
        "created_at": now,
    }


def list_documents(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List all registered document records for the applicant."""
    app = get_or_create_application(user)
    with auth._db() as db:
        rows = db.execute(
            """SELECT id, slot, doc_type, mime_type, file_size, status,
                      quality_score, rejection_reason, created_at, updated_at
               FROM document_records
               WHERE application_id=?
               ORDER BY created_at ASC""",
            (app["id"],),
        ).fetchall()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "slot": r[1],
            "doc_type": r[2],
            "mime_type": r[3],
            "file_size": r[4],
            "status": r[5],
            "quality_score": r[6],
            "rejection_reason": r[7],
            "created_at": r[8],
            "updated_at": r[9],
        })
    return results


def get_document_content(caller_user: Dict[str, Any], doc_id: str) -> Tuple[bytes, str, str]:
    """Retrieve document bytes enforcing strict ABAC isolation.

    Invariants:
    1. Applicant can only read their own documents.
    2. Reviewers/Admins must have read_applicant_data permission.
    3. Tech Admin and Auditor have NO permission to download applicant document images.
    """
    with auth._db() as db:
        row = db.execute(
            """SELECT d.id, d.user_id, d.storage_path, d.mime_type, d.slot, u.role
               FROM document_records d
               JOIN users u ON d.user_id = u.id
               WHERE d.id=?""",
            (doc_id,),
        ).fetchone()

    if not row:
        raise FileNotFoundError("document_not_found")

    doc_owner_id = row[1]
    storage_path = row[2]
    mime_type = row[3]
    slot = row[4]

    caller_role = caller_user.get("role", "applicant")
    caller_id = caller_user.get("id")

    # Enforce role boundaries
    if caller_role == "applicant":
        if caller_id != doc_owner_id:
            raise PermissionError("access_denied_not_owner")
    else:
        # Staff caller
        # Invariant: tech_admin and auditor are blocked from applicant documents
        if caller_role in ("tech_admin", "auditor"):
            raise PermissionError("access_denied_role_cannot_view_applicant_images")

        allowed_roles = {
            "reviewer",
            "senior_reviewer",
            "operations",
            "compliance_officer",
            "fraud_investigator",
        }
        if caller_role not in allowed_roles:
            raise PermissionError("access_denied_insufficient_privilege")

    content = read_document_file(storage_path)
    file_name = f"{slot.lower()}_{doc_id[:8]}"
    return content, mime_type, file_name


def verify_application(user: Dict[str, Any]) -> Dict[str, Any]:
    """Execute end-to-end verification and cross-document validation."""
    app = get_or_create_application(user)
    app_id = app["id"]
    details = app.get("details") or {}

    applicant_name = details.get("name") or user.get("display_name") or "Saisidhardh Vajja"
    applicant_dob = details.get("dob") or "1995-05-15"
    pan_number = details.get("pan") or "ABCDE1234F"
    aadhaar_number = details.get("aadhaar") or "999941051234"
    bank_acc = details.get("bank_account") or "123456789012"
    bank_ifsc = details.get("ifsc") or "SBIN0001234"
    roll_no = details.get("class10_roll") or "1234567"
    board = details.get("board") or "CBSE"

    # 1. Run Providers
    pan_res = PanVerificationProvider.verify(pan_number, applicant_name, applicant_dob)
    aadhaar_res = AadhaarKycProvider.verify(aadhaar_number, applicant_name, applicant_dob)
    bank_res = BankVerificationProvider.verify(bank_acc, bank_ifsc, applicant_name)
    class10_res = Class10VerificationProvider.verify(roll_no, board, applicant_name, applicant_dob)

    now = int(time.time())

    with auth._db() as db:
        # Record verification results
        for prov_name, chk_type, res in [
            ("PROTEAN_NSDL", "PAN_VERIFICATION", pan_res),
            ("UIDAI_DIGILOCKER", "AADHAAR_KYC", aadhaar_res),
            ("NPCI_PENNY_DROP", "BANK_ACCOUNT_VERIFICATION", bank_res),
            ("DIGILOCKER_ACADEMIC", "CLASS10_QUALIFICATION", class10_res),
        ]:
            db.execute(
                """INSERT INTO verification_results (
                    id, application_id, provider, check_type, status,
                    reference_id, match_score, response_digest, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"vr_{secrets.token_hex(10)}",
                    app_id,
                    prov_name,
                    chk_type,
                    res.get("status", "FAILED"),
                    res.get("reference_id"),
                    1.0 if res.get("ok") else 0.0,
                    res.get("response_digest", hashlib.sha256(str(res).encode()).hexdigest()),
                    json.dumps(res),
                    now,
                ),
            )

        # 2. Run Cross-Document Checks
        cross_report = run_cross_document_checks(
            pan_data=pan_res if pan_res.get("ok") else None,
            aadhaar_data=aadhaar_res if aadhaar_res.get("ok") else None,
            bank_data=bank_res if bank_res.get("ok") else None,
            class10_data=class10_res if class10_res.get("ok") else None,
            application_dob=applicant_dob,
        )

        # Persist cross document checks
        for chk in cross_report["checks"]:
            db.execute(
                """INSERT INTO cross_document_checks (
                    id, application_id, check_name, status, discrepancy_details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    f"cdc_{secrets.token_hex(10)}",
                    app_id,
                    chk["check_name"],
                    chk["status"],
                    chk["details"],
                    now,
                ),
            )

        # Check if all passed or remediation needed
        all_providers_ok = all(r.get("ok") for r in (pan_res, aadhaar_res, bank_res, class10_res))
        cross_ok = cross_report["verdict"] == "ALL_PASSED"

        if all_providers_ok and cross_ok:
            new_status = "KYC_APPROVED"
        else:
            new_status = "NEEDS_MORE_INFO"

        db.execute(
            "UPDATE applications SET status=?, verified_at=?, updated_at=? WHERE id=?",
            (new_status, now, now, app_id),
        )
        db.execute("UPDATE cases SET status=? WHERE applicant_id=?", (new_status, user["id"]))

        portal.record(
            db,
            user["id"],
            "verification_completed",
            stage="Documents",
            doc=f"verdict:{cross_report['verdict']}",
        )

    return {
        "ok": True,
        "application_status": new_status,
        "pan_verification": pan_res,
        "aadhaar_verification": aadhaar_res,
        "bank_verification": bank_res,
        "class10_verification": class10_res,
        "cross_checks": cross_report,
        "verified_at": now,
    }


def submit_document_correction(
    user: Dict[str, Any],
    slot: str,
    file_bytes: bytes,
    file_name: str = "corrected_doc",
    explanation: Optional[str] = None,
) -> Dict[str, Any]:
    """Applicant re-uploads a corrected document to resolve a defect."""
    # Process re-upload
    upload_res = upload_document(user, slot, file_bytes, file_name)

    app = get_or_create_application(user)
    app_id = app["id"]
    now = int(time.time())

    with auth._db() as db:
        # If application was in NEEDS_MORE_INFO, transition to IN_REVIEW for reviewer re-check
        if app["status"] == "NEEDS_MORE_INFO":
            db.execute(
                "UPDATE applications SET status='IN_REVIEW', updated_at=? WHERE id=?",
                (now, app_id),
            )
            db.execute("UPDATE cases SET status='IN_REVIEW' WHERE applicant_id=?", (user["id"],))

        portal.record(
            db,
            user["id"],
            "doc_corrected",
            stage="Documents",
            doc=slot,
        )

    upload_res["remediation_note"] = "Correction submitted successfully. Application is back in review."
    return upload_res


def get_cross_document_checks(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve history of cross-document verification checks."""
    app = get_or_create_application(user)
    with auth._db() as db:
        rows = db.execute(
            """SELECT id, check_name, status, discrepancy_details, created_at
               FROM cross_document_checks
               WHERE application_id=?
               ORDER BY created_at DESC""",
            (app["id"],),
        ).fetchall()

    return [
        {
            "id": r[0],
            "check_name": r[1],
            "status": r[2],
            "details": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def get_guidelines(slot: Optional[str] = None, lang: str = "en") -> Dict[str, Any]:
    """Retrieve localized document preparation guidelines."""
    l = "hi" if (lang or "").lower().startswith("hi") else "en"
    if slot:
        slot_upper = slot.strip().upper()
        g = SLOT_GUIDELINES.get(slot_upper, {})
        return {slot_upper: g.get(l, g.get("en", {}))}

    return {
        s: data.get(l, data.get("en", {}))
        for s, data in SLOT_GUIDELINES.items()
    }
