"""IRDAI Digital POSP Certification & Public Verification Engine.

Complies with:
1. IRDAI Guidelines for Point of Sales Person (Life & General Insurance) 2015.
2. Section 41 of Insurance Act 1938 (Prohibition of Rebates).
3. Section 65B of Indian Evidence Act (Digital Signatures & Tamper-Evident Records).

Features:
- Mandatory pre-requisites: KYC approved, 15 hours training complete, Exam passed.
- Standardized IRDAI POSP Appointment Agreement with digital e-Sign acknowledgment.
- Unique POSP Code generation: PN-POSP-YYYY-XXXXX.
- Tamper-Evident HMAC-SHA256 Cryptographic Digital Signature.
- Zero-Auth Public Verification Portal (/api/certificates/verify/<id>).
- Certificate Administrator lifecycle: view, audit, revoke with disciplinary reasons.
- Renderable SVG Certificate with official PolicyNest seal and security watermark.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import policy
import portal

log = logging.getLogger("policynest.certification")

SECRET_SIGNING_KEY = os.environ.get(
    "CERTIFICATE_SECRET", "policynest_posp_master_signature_key_2026_secured"
).encode("utf-8")

ISSUING_ENTITY = "PolicyNest Broking Technologies Pvt. Ltd."
IRDAI_REGISTRATION_NO = "IRDAI/DB/891/2021 (Direct Broker - Life & General)"
VALIDITY_YEARS = 3  # Standard 3-year POSP appointment validity


def _check_cert_access(actor: Dict[str, Any], action: str = "certificate.read") -> None:
    """Enforce ABAC capability check for certification operations."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    resource = {"applicant_id": actor["id"], "sensitivity": "applicant"}

    if role == "applicant":
        if not policy.allows(actor, action, resource):
            raise PermissionError(f"forbidden: applicant lacks '{action}'")
    elif role in ("certificate_admin", "compliance_officer", "tech_admin", "admin"):
        return  # Authorized staff personas
    else:
        raise PermissionError(f"forbidden: role '{role}' lacks certificate access")


def compute_certificate_signature(
    cert_number: str,
    user_id: int,
    posp_name: str,
    pan_masked: str,
    issued_at: int,
    valid_until: int,
    lines_of_business: str,
) -> str:
    """Compute HMAC-SHA256 cryptographic signature digest over certificate fields."""
    payload = f"{cert_number}|{user_id}|{posp_name}|{pan_masked}|{issued_at}|{valid_until}|{lines_of_business}"
    return hmac.new(SECRET_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_certificate_signature(cert_row: Dict[str, Any]) -> bool:
    """Verify that a stored certificate row matches its cryptographic HMAC signature."""
    expected = compute_certificate_signature(
        cert_row["certificate_number"],
        cert_row["user_id"],
        cert_row["posp_name"],
        cert_row["pan_masked"],
        cert_row["issued_at"],
        cert_row["valid_until"],
        cert_row["lines_of_business"],
    )
    return hmac.compare_digest(expected, cert_row["signature_digest"])


# ------------------------------------------------------------- Eligibility
def get_certificate_eligibility(user: Dict[str, Any], db=None) -> Dict[str, Any]:
    """Check if applicant has passed the exam and completed all pre-requisites."""
    _check_cert_access(user, "certificate.read")
    user_id = user["id"]

    def _eval(conn):
        app_row = conn.execute(
            "SELECT id, status, stage, details, progress FROM applications WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if not app_row:
            return {"eligible": False, "reason": "APPLICATION_NOT_FOUND"}

        app_status = app_row["status"]

        # Check existing certificate
        cert_row = conn.execute(
            "SELECT * FROM certificates WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if cert_row:
            return {
                "eligible": True,
                "already_certified": True,
                "status": cert_row["status"],
                "certificate_number": cert_row["certificate_number"],
                "issued_at": cert_row["issued_at"],
                "valid_until": cert_row["valid_until"],
                "lines_of_business": cert_row["lines_of_business"].split(","),
            }

        # Check exam passed status
        if app_status not in ("EXAM_PASSED", "AGREEMENT_EXECUTED", "CERTIFIED"):
            return {
                "eligible": False,
                "already_certified": False,
                "reason": "EXAM_NOT_PASSED",
                "current_status": app_status,
                "message": "You must successfully pass the POSP Certification Exam before certification.",
            }

        # Check agreement status
        agree_row = conn.execute(
            "SELECT id, signed_at, agreement_hash FROM posp_agreements WHERE user_id=?",
            (user_id,),
        ).fetchone()

        agreement_completed = agree_row is not None

        return {
            "eligible": True,
            "already_certified": False,
            "agreement_completed": agreement_completed,
            "agreement_id": agree_row["id"] if agree_row else None,
            "can_execute_agreement": not agreement_completed,
            "can_issue_certificate": agreement_completed,
            "message": "Eligible for POSP Appointment and Digital Certification.",
        }

    if db is not None:
        return _eval(db)

    with auth._db() as db_conn:
        return _eval(db_conn)


# ------------------------------------------------------------- Agreement Template
def get_posp_agreement_template(user: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """Return the bilingual IRDAI POSP Appointment Agreement text and terms."""
    _check_cert_access(user, "certificate.read")
    user_id = user["id"]

    with auth._db() as db:
        user_row = db.execute("SELECT display_name, email FROM users WHERE id=?", (user_id,)).fetchone()
        app_row = db.execute("SELECT details FROM applications WHERE user_id=?", (user_id,)).fetchone()

    name = user_row["display_name"] if user_row else "Candidate"
    details = json.loads(app_row["details"]) if (app_row and app_row["details"]) else {}
    pan = details.get("pan_masked", "ABCDE****F")

    clauses_en = [
        {
            "clause": "1. Appointment & Authority",
            "text": f"PolicyNest Broking Technologies Pvt. Ltd. (IRDAI Direct Broker) appoints {name} ('POSP') as an authorized Point of Sales Person under IRDAI Guidelines for POSP 2015 to solicit and market pre-underwritten retail insurance products.",
        },
        {
            "clause": "2. Authorized Lines of Business",
            "text": "The POSP is authorized to solicit POSP-specified products across: (a) Life Insurance (Pure Term, Endowment, Savings); (b) General Insurance (Motor Comprehensive & Third Party, Home, Personal Accident, Travel); (c) Health Insurance (Individual and Floater indemnity plans).",
        },
        {
            "clause": "3. Single Affiliation Undertaking",
            "text": "In compliance with IRDAI POSP Guidelines, the POSP explicitly declares and covenants that they are not currently appointed or acting as an insurance agent, POSP, or corporate agent with any other insurer or insurance intermediary.",
        },
        {
            "clause": "4. Section 41 Prohibition of Rebates",
            "text": "The POSP strictly undertakes compliance with Section 41 of the Insurance Act 1938. No person shall allow or offer to allow, either directly or indirectly, as an inducement to any person to take out or renew or continue an insurance policy, any rebate of the whole or part of the commission payable.",
        },
        {
            "clause": "5. Code of Conduct & Client Best Interest",
            "text": "The POSP covenants to act with utmost good faith, disclose all material policy exclusions and terms truthfully, protect client privacy under DPDP Act 2023, and never misrepresent policy features or benefits.",
        },
        {
            "clause": "6. Remuneration & Commission Transparency",
            "text": "Commissions shall be credited directly to the verified bank account of the POSP per the standard IRDAI commission schedule without unlawful deductions.",
        },
        {
            "clause": "7. Termination & Disciplinary Action",
            "text": "PolicyNest reserves the right to terminate this appointment immediately upon breach of IRDAI regulations, fraud, criminal conviction, or misrepresentation, with formal notification to the IRDAI central repository.",
        },
    ]

    clauses_hi = [
        {
            "clause": "1. नियुक्ति और अधिकार",
            "text": f"पॉलिसीनस्ट ब्रोकिंग टेक्नोलॉजीज प्राइवेट लिमिटेड (IRDAI डायरेक्ट ब्रोकर) {name} ('POSP') को IRDAI POSP दिशानिर्देश 2015 के तहत अधिकृत पॉइंट ऑफ सेल्स पर्सन के रूप में नियुक्त करता है।",
        },
        {
            "clause": "2. अधिकृत व्यवसाय क्षेत्र",
            "text": "POSP को (क) जीवन बीमा (प्योर टर्म, एंडोमेंट); (ख) सामान्य बीमा (मोटर, गृह, व्यक्तिगत दुर्घटना, यात्रा); और (ग) स्वास्थ्य बीमा योजनाओं के विपणन का अधिकार है।",
        },
        {
            "clause": "3. एकल संबद्धता वचनबद्धता",
            "text": "POSP घोषणा करता है कि वह किसी अन्य बीमा कंपनी या मध्यस्थ के साथ बीमा एजेंट या POSP के रूप में संबद्ध नहीं है।",
        },
        {
            "clause": "4. धारा 41 रिबेट निषेध",
            "text": "POSP बीमा अधिनियम 1938 की धारा 41 का कड़ाई से पालन करने का वचन देता है। किसी भी ग्राहक को प्रत्यक्ष या अप्रत्यक्ष रूप से कमीशन में छूट देना पूर्णतः प्रतिबंधित है।",
        },
        {
            "clause": "5. आचार संहिता और गोपनीयता",
            "text": "POSP परम सद्भाव से कार्य करने, सभी शर्तों का खुलासा करने और ग्राहक डेटा की पूर्ण गोपनीयता बनाए रखने का वचन देता है।",
        },
    ]

    selected_clauses = clauses_hi if lang == "hi" else clauses_en

    return {
        "ok": True,
        "agreement_type": "IRDAI_POSP_APPOINTMENT_AGREEMENT",
        "version": "2026.1",
        "candidate_name": name,
        "pan_masked": pan,
        "issuing_entity": ISSUING_ENTITY,
        "reg_no": IRDAI_REGISTRATION_NO,
        "clauses": selected_clauses,
        "statutory_declaration": (
            "I hereby confirm that I have read and agree to all terms of the POSP Appointment Agreement and IRDAI Code of Conduct."
            if lang != "hi"
            else "मैं पुष्टि करता हूँ कि मैंने POSP नियुक्ति अनुबंध और IRDAI आचार संहिता की सभी शर्तों को पढ़ और स्वीकार कर लिया है।"
        ),
    }


# ------------------------------------------------------------- Execute Agreement
def execute_posp_agreement(
    user: Dict[str, Any],
    declaration_accepted: bool = True,
    client_ip: str = "127.0.0.1",
) -> Dict[str, Any]:
    """Execute digital POSP Appointment Agreement with Aadhaar e-Sign simulation."""
    _check_cert_access(user, "agreement.execute")
    if not declaration_accepted:
        raise ValueError("declaration_must_be_accepted")

    user_id = user["id"]
    now = int(time.time())

    with auth._db() as db:
        eligibility = get_certificate_eligibility(user, db=db)
        if not eligibility["eligible"]:
            raise ValueError(f"ineligible_for_agreement:{eligibility.get('reason')}")

        # Check if already executed
        existing = db.execute(
            "SELECT * FROM posp_agreements WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if existing:
            return {
                "ok": True,
                "agreement_id": existing["id"],
                "signed_at": existing["signed_at"],
                "agreement_hash": existing["agreement_hash"],
                "status": "ALREADY_EXECUTED",
            }

        # Retrieve applicant name and details
        user_row = db.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
        app_row = db.execute("SELECT id, details, progress FROM applications WHERE user_id=?", (user_id,)).fetchone()

        app_id = app_row["id"]
        signer_name = user_row["display_name"] if user_row else "POSP Candidate"
        details = json.loads(app_row["details"]) if (app_row and app_row["details"]) else {}
        pan_masked = details.get("pan_masked", "ABCDE****F")

        # Generate agreement ID and hash
        agree_id = f"AGREE-{time.strftime('%Y')}-{user_id}-{secrets.token_hex(4)}"
        hash_payload = f"{agree_id}|{user_id}|{signer_name}|{pan_masked}|{now}|{client_ip}"
        agree_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

        db.execute(
            """INSERT INTO posp_agreements (
                id, user_id, application_id, agreement_type, version,
                terms_accepted, code_of_conduct_accepted, anti_rebating_declared,
                signer_name, signer_ip, signed_at, agreement_hash,
                counter_signed_by, counter_signed_at
            ) VALUES (?, ?, ?, 'IRDAI_POSP_APPOINTMENT', '2026.1', 1, 1, 1, ?, ?, ?, ?, 'Principal Officer, PolicyNest Broking Technologies', ?)""",
            (agree_id, user_id, app_id, signer_name, client_ip, now, agree_hash, now),
        )

        # Update application state
        progress = json.loads(app_row["progress"] or "{}")
        progress["agreement"] = {
            "agreement_id": agree_id,
            "signed_at": now,
            "agreement_hash": agree_hash,
        }

        db.execute(
            """UPDATE applications
               SET status='AGREEMENT_EXECUTED', progress=?, updated_at=?
               WHERE id=?""",
            (json.dumps(progress), now, app_id),
        )

        portal.record(db, user_id, "agreement_executed", stage="Certificate")
        db.execute(
            """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
               VALUES (?, 'success', 'agreement_executed', 'Certificate', '', '#certificate', 0, ?, ?)""",
            (user_id, now, f"PN-{app_id}"),
        )

    return {
        "ok": True,
        "agreement_id": agree_id,
        "signer_name": signer_name,
        "signed_at": now,
        "agreement_hash": agree_hash,
        "status": "AGREEMENT_EXECUTED",
    }


# ------------------------------------------------------------- Issue Certificate
def issue_posp_certificate(
    user: Dict[str, Any],
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Authoritatively issue a tamper-evident digital POSP Certificate with HMAC-SHA256 signature."""
    executing_actor = actor or user
    _check_cert_access(executing_actor, "certificate.issue" if actor else "certificate.read")

    user_id = user["id"]
    now = int(time.time())
    valid_until = now + (VALIDITY_YEARS * 365 * 86400)
    current_year = time.strftime("%Y")

    with auth._db() as db:
        # Check if already issued
        existing_cert = db.execute(
            "SELECT * FROM certificates WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if existing_cert:
            return _format_certificate_response(dict(existing_cert))

        # Check prerequisites
        app_row = db.execute("SELECT id, status, details, progress FROM applications WHERE user_id=?", (user_id,)).fetchone()
        if not app_row:
            raise FileNotFoundError("application_not_found")

        app_id = app_row["id"]
        app_status = app_row["status"]

        if app_status not in ("EXAM_PASSED", "AGREEMENT_EXECUTED"):
            raise ValueError(f"prerequisites_not_met: status is '{app_status}'")

        # Verify agreement executed
        agree_row = db.execute("SELECT id FROM posp_agreements WHERE user_id=?", (user_id,)).fetchone()
        if not agree_row:
            raise ValueError("agreement_must_be_executed_before_issuing_certificate")

        # Fetch candidate legal name and masked PAN
        user_row = db.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
        posp_name = user_row["display_name"] if user_row else "Certified POSP"

        details = json.loads(app_row["details"]) if app_row["details"] else {}
        pan_masked = details.get("pan_masked", "ABCDE****F")
        lines_of_business = "Life,General,Health"

        # Sequential certificate counter
        cert_count = db.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
        seq_num = cert_count + 1
        cert_number = f"PN-POSP-{current_year}-{seq_num:05d}"
        cert_id = f"CERT-{current_year}-{seq_num:05d}"

        # Compute cryptographic signature
        signature_digest = compute_certificate_signature(
            cert_number=cert_number,
            user_id=user_id,
            posp_name=posp_name,
            pan_masked=pan_masked,
            issued_at=now,
            valid_until=valid_until,
            lines_of_business=lines_of_business,
        )

        db.execute(
            """INSERT INTO certificates (
                id, certificate_number, user_id, application_id,
                posp_name, pan_masked, lines_of_business,
                issued_at, valid_until, status, signature_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)""",
            (
                cert_id,
                cert_number,
                user_id,
                app_id,
                posp_name,
                pan_masked,
                lines_of_business,
                now,
                valid_until,
                signature_digest,
            ),
        )

        # Update application status to CERTIFIED and stage to Certified
        progress = json.loads(app_row["progress"] or "{}")
        progress["certificate"] = {
            "certificate_id": cert_id,
            "certificate_number": cert_number,
            "issued_at": now,
            "valid_until": valid_until,
            "signature_digest": signature_digest,
            "status": "ACTIVE",
        }

        db.execute(
            """UPDATE applications
               SET status='CERTIFIED', stage='Certified', progress=?, updated_at=?
               WHERE id=?""",
            (json.dumps(progress), now, app_id),
        )

        db.execute("UPDATE cases SET status='CERTIFIED' WHERE applicant_id=?", (user_id,))
        portal.record(db, user_id, "certificate_issued", stage="Certified")

        db.execute(
            """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
               VALUES (?, 'success', 'certificate_issued', 'Certified', '', '#certificate', 0, ?, ?)""",
            (user_id, now, cert_number),
        )

        db.execute(
            """INSERT INTO audit_events (case_id, actor_id, action, occurred)
               VALUES (?, ?, 'CERTIFICATE_ISSUED', ?)""",
            (f"user_{user_id}", executing_actor["id"], now),
        )

        cert_dict = {
            "id": cert_id,
            "certificate_number": cert_number,
            "user_id": user_id,
            "application_id": app_id,
            "posp_name": posp_name,
            "pan_masked": pan_masked,
            "lines_of_business": lines_of_business,
            "issued_at": now,
            "valid_until": valid_until,
            "status": "ACTIVE",
            "signature_digest": signature_digest,
        }

    return _format_certificate_response(cert_dict)


def get_user_certificate(user: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the digital certificate for the authenticated applicant."""
    _check_cert_access(user, "certificate.read")
    user_id = user["id"]

    with auth._db() as db:
        cert_row = db.execute("SELECT * FROM certificates WHERE user_id=?", (user_id,)).fetchone()
        if not cert_row:
            raise FileNotFoundError("certificate_not_found")
        return _format_certificate_response(dict(cert_row))


# ------------------------------------------------------------- Zero-Auth Public Verification
def verify_certificate_public(identifier: str) -> Dict[str, Any]:
    """Zero-auth public endpoint to verify certificate authenticity and tamper integrity."""
    clean_id = (identifier or "").strip().upper()
    if not clean_id:
        return {"verified": False, "status": "INVALID_QUERY", "message": "Identifier required"}

    with auth._db() as db:
        cert_row = db.execute(
            """SELECT * FROM certificates
               WHERE UPPER(certificate_number)=? OR UPPER(id)=?""",
            (clean_id, clean_id),
        ).fetchone()

        if not cert_row:
            return {
                "verified": False,
                "status": "NOT_FOUND",
                "message": f"No POSP certificate matches identifier '{identifier}'.",
            }

        cert = dict(cert_row)

        # Cryptographically check HMAC-SHA256 signature
        is_tamper_free = verify_certificate_signature(cert)
        if not is_tamper_free:
            return {
                "verified": False,
                "status": "TAMPERED",
                "certificate_number": cert["certificate_number"],
                "message": "SECURITY ALERT: Digital signature verification failed! Tamper detected.",
            }

        if cert["status"] == "REVOKED":
            return {
                "verified": True,
                "status": "REVOKED",
                "certificate_number": cert["certificate_number"],
                "holder_name": cert["posp_name"],
                "pan_masked": cert["pan_masked"],
                "revoked_at": cert["revoked_at"],
                "revocation_reason": cert["revocation_reason"],
                "message": "Certificate was formally revoked and is NO LONGER VALID.",
            }

        return {
            "verified": True,
            "status": cert["status"],
            "certificate_number": cert["certificate_number"],
            "certificate_id": cert["id"],
            "holder_name": cert["posp_name"],
            "pan_masked": cert["pan_masked"],
            "lines_of_business": cert["lines_of_business"].split(","),
            "issuing_entity": ISSUING_ENTITY,
            "registration_number": IRDAI_REGISTRATION_NO,
            "issued_at": cert["issued_at"],
            "valid_until": cert["valid_until"],
            "tamper_check": "VALID",
            "signature_digest_prefix": cert["signature_digest"][:16] + "...",
            "verification_seal": "IRDAI_POSP_OFFICIAL_VERIFIED",
        }


# ------------------------------------------------------------- Certificate Admin Operations
def admin_list_certificates(
    actor: Dict[str, Any],
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List issued certificates for Certificate Administrator console."""
    _check_cert_access(actor, "certificate.verify")

    query = "SELECT * FROM certificates WHERE 1=1"
    args = []
    if status:
        query += " AND status=?"
        args.append(status.upper())
    query += " ORDER BY issued_at DESC LIMIT ?"
    args.append(max(1, min(limit, 100)))

    with auth._db() as db:
        rows = db.execute(query, args).fetchall()
        return [dict(r) for r in rows]


def admin_revoke_certificate(
    actor: Dict[str, Any],
    cert_id_or_number: str,
    reason: str,
) -> Dict[str, Any]:
    """Revoke an active POSP certificate with disciplinary reason and audit trail."""
    _check_cert_access(actor, "certificate.revoke")
    now = int(time.time())
    clean_id = (cert_id_or_number or "").strip().upper()

    with auth._db() as db:
        cert_row = db.execute(
            "SELECT * FROM certificates WHERE UPPER(certificate_number)=? OR UPPER(id)=?",
            (clean_id, clean_id),
        ).fetchone()

        if not cert_row:
            raise FileNotFoundError("certificate_not_found")

        cert = dict(cert_row)
        user_id = cert["user_id"]
        cert_id = cert["id"]
        cert_number = cert["certificate_number"]

        db.execute(
            """UPDATE certificates
               SET status='REVOKED', revoked_at=?, revocation_reason=?
               WHERE id=?""",
            (now, reason, cert_id),
        )

        # Update application status
        db.execute(
            """UPDATE applications
               SET status='REVOKED', updated_at=?
               WHERE user_id=?""",
            (now, user_id),
        )

        db.execute("UPDATE cases SET status='REVOKED' WHERE applicant_id=?", (user_id,))

        db.execute(
            """INSERT INTO audit_events (case_id, actor_id, action, occurred)
               VALUES (?, ?, 'CERTIFICATE_REVOKED', ?)""",
            (f"user_{user_id}", actor["id"], now),
        )

        db.execute(
            """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
               VALUES (?, 'error', 'certificate_revoked', 'Certified', '', '#status', 0, ?, ?)""",
            (user_id, now, cert_number),
        )

    return {
        "ok": True,
        "certificate_number": cert_number,
        "status": "REVOKED",
        "revoked_at": now,
        "reason": reason,
    }


def _format_certificate_response(cert: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to structure clean certificate output dictionary."""
    is_tamper_free = verify_certificate_signature(cert)
    return {
        "ok": True,
        "id": cert["id"],
        "certificate_number": cert["certificate_number"],
        "holder_name": cert["posp_name"],
        "pan_masked": cert["pan_masked"],
        "lines_of_business": cert["lines_of_business"].split(","),
        "issuing_entity": ISSUING_ENTITY,
        "registration_number": IRDAI_REGISTRATION_NO,
        "issued_at": cert["issued_at"],
        "valid_until": cert["valid_until"],
        "status": cert["status"],
        "signature_digest": cert["signature_digest"],
        "signature_valid": is_tamper_free,
        "public_verify_url": f"/api/certificates/verify/{cert['certificate_number']}",
    }


def render_certificate_svg(cert_data: Dict[str, Any]) -> str:
    """Render an official SVG certificate matching Embarko branding and IRDAI standards."""
    name = cert_data.get("holder_name", "POSP Candidate")
    cert_no = cert_data.get("certificate_number", "PN-POSP-XXXX")
    pan = cert_data.get("pan_masked", "ABCDE****F")
    issued = time.strftime("%d %b %Y", time.gmtime(cert_data.get("issued_at", int(time.time()))))
    valid = time.strftime("%d %b %Y", time.gmtime(cert_data.get("valid_until", int(time.time()) + 94608000)))
    sig_digest = cert_data.get("signature_digest", "")[:24] + "..."

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700" width="1000" height="700">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a192f"/>
      <stop offset="100%" stop-color="#0f2b48"/>
    </linearGradient>
    <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f6d365"/>
      <stop offset="100%" stop-color="#fda085"/>
    </linearGradient>
  </defs>

  <!-- Border & Background -->
  <rect width="1000" height="700" fill="url(#bg)" rx="16"/>
  <rect x="24" y="24" width="952" height="652" fill="none" stroke="url(#gold)" stroke-width="4" rx="12"/>
  <rect x="36" y="36" width="928" height="628" fill="none" stroke="#233554" stroke-width="1.5" rx="8"/>

  <!-- Header -->
  <text x="500" y="90" text-anchor="middle" fill="#64ffda" font-family="system-ui, sans-serif" font-size="14" letter-spacing="4" font-weight="bold">POLICYNEST BROKING TECHNOLOGIES</text>
  <text x="500" y="115" text-anchor="middle" fill="#8892b0" font-family="system-ui, sans-serif" font-size="12">IRDAI Direct Broker Reg: DB 891/21 | Point of Sales Person (POSP) Registry</text>

  <text x="500" y="180" text-anchor="middle" fill="url(#gold)" font-family="Georgia, serif" font-size="34" font-weight="bold">Certificate of Appointment</text>
  <text x="500" y="215" text-anchor="middle" fill="#ccd6f6" font-family="system-ui, sans-serif" font-size="15">This certifies that under the IRDAI Guidelines for POSP 2015</text>

  <!-- Candidate Name -->
  <text x="500" y="280" text-anchor="middle" fill="#ffffff" font-family="Georgia, serif" font-size="36" font-weight="bold">{name}</text>
  <line x1="300" y1="298" x2="700" y2="298" stroke="url(#gold)" stroke-width="2"/>

  <!-- Body -->
  <text x="500" y="340" text-anchor="middle" fill="#a8b2d1" font-family="system-ui, sans-serif" font-size="14">has successfully completed 15 hours of mandated training, passed the certification assessment,</text>
  <text x="500" y="365" text-anchor="middle" fill="#a8b2d1" font-family="system-ui, sans-serif" font-size="14">and executed the appointment agreement as an authorized Point of Sales Person (POSP).</text>

  <!-- Authorized Lines of Business -->
  <rect x="250" y="395" width="500" height="42" fill="#112240" rx="6" stroke="#233554"/>
  <text x="500" y="422" text-anchor="middle" fill="#64ffda" font-family="system-ui, sans-serif" font-size="14" font-weight="600">Authorized Lines: Life (Pure Term) • General (Motor/Travel/Home) • Health</text>

  <!-- Details Grid -->
  <text x="180" y="485" fill="#8892b0" font-family="system-ui, sans-serif" font-size="12">POSP CERTIFICATE NO.</text>
  <text x="180" y="510" fill="#ffffff" font-family="monospace" font-size="15" font-weight="bold">{cert_no}</text>

  <text x="440" y="485" fill="#8892b0" font-family="system-ui, sans-serif" font-size="12">IDENTIFIER (PAN)</text>
  <text x="440" y="510" fill="#ffffff" font-family="monospace" font-size="15" font-weight="bold">{pan}</text>

  <text x="700" y="485" fill="#8892b0" font-family="system-ui, sans-serif" font-size="12">ISSUANCE &amp; EXPIRY</text>
  <text x="700" y="510" fill="#ffffff" font-family="system-ui, sans-serif" font-size="13">{issued} — {valid}</text>

  <!-- Cryptographic Seal Footer -->
  <line x1="100" y1="560" x2="900" y2="560" stroke="#233554" stroke-width="1"/>
  <circle cx="150" cy="605" r="28" fill="#112240" stroke="url(#gold)" stroke-width="2"/>
  <text x="150" y="610" text-anchor="middle" fill="#f6d365" font-family="system-ui, sans-serif" font-size="18" font-weight="bold">IRDAI</text>

  <text x="200" y="598" fill="#64ffda" font-family="system-ui, sans-serif" font-size="12" font-weight="bold">DIGITALLY VERIFIED POSP REGISTRATION</text>
  <text x="200" y="618" fill="#8892b0" font-family="monospace" font-size="10">HMAC-SHA256: {sig_digest}</text>

  <text x="760" y="605" text-anchor="middle" fill="#ffffff" font-family="Georgia, serif" font-size="14" font-weight="bold">Principal Officer</text>
  <text x="760" y="622" text-anchor="middle" fill="#8892b0" font-family="system-ui, sans-serif" font-size="11">PolicyNest Broking Technologies</text>
</svg>"""
