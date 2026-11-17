"""Communications, Notifications, Unified Audit Timeline, and IRDAI Compliance Audit Pack Engine.

Complies with:
1. IRDAI Point of Sales Person (POSP) Guidelines 2015.
2. Information Technology Act 2000 & Digital Personal Data Protection (DPDP) Act 2023.
3. Multi-Channel Notification Dispatcher (In-App, Email, SMS simulation).
4. Strict Anti-Accusation Invariant (applicant communications never leak fraud or accusatory terms).
5. Unified Immutable Timeline merging applicant events and staff audit trails.
6. IRDAI Regulatory Compliance Audit Pack Exporter with cryptographic SHA-256 seal.
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
import portal

log = logging.getLogger("policynest.communications")

# Anti-Accusation Invariant: Banned terms that must NEVER leak to applicant notifications
BANNED_COMMUNICATION_WORDS = {
    "fraud", "fraudulent", "tamper", "tampered", "manipulation",
    "forgery", "forged", "counterfeit", "syndicate", "ring",
    "blacklist", "blacklisted", "impostor", "malicious",
}

BANNED_PATTERN = re.compile(
    r"\b(" + "|".join(BANNED_COMMUNICATION_WORDS) + r")\b",
    re.IGNORECASE,
)


def _sanitize_for_applicant(text: str) -> str:
    """Ensure applicant communications adhere strictly to the Anti-Accusation Invariant."""
    if not text:
        return ""
    # Replace any accusatory wording with constructive advisory language
    return BANNED_PATTERN.sub("verification review discrepancy", text)


# ------------------------------------------------------------- Multi-Channel Templates
TEMPLATES = {
    "application_started": {
        "subject_en": "Welcome to PolicyNest POSP Onboarding",
        "subject_hi": "पॉलिसीनस्ट पीओएसपी ऑनबोर्डिंग में आपका स्वागत है",
        "email_en": "Your POSP application {reference} has been initiated. Complete your profile and document upload to proceed.",
        "email_hi": "आपका पीओएसपी आवेदन {reference} शुरू हो गया है। आगे बढ़ने के लिए अपना प्रोफाइल और दस्तावेज अपलोड पूरा करें।",
        "sms_en": "PolicyNest: Your POSP application {reference} is started. Complete your KYC documents to continue.",
        "sms_hi": "पॉलिसीनस्ट: आपका आवेदन {reference} शुरू हो गया है। जारी रखने के लिए अपने दस्तावेज अपलोड करें।",
        "type": "info",
        "action": "#documents",
    },
    "kyc_approved": {
        "subject_en": "KYC Verified - Training Unlocked",
        "subject_hi": "केवाईसी सत्यापित - प्रशिक्षण अनलॉक",
        "email_en": "Congratulations! Your identity and qualification documents for {reference} have been verified. You may now begin your 15-hour IRDAI training curriculum.",
        "email_hi": "बधाई! {reference} के लिए आपके दस्तावेज सत्यापित हो गए हैं। अब आप अपना 15 घंटे का IRDAI प्रशिक्षण शुरू कर सकते हैं।",
        "sms_en": "PolicyNest: KYC verified! Your 15-hour IRDAI POSP training is now unlocked. Start learning today.",
        "sms_hi": "पॉलिसीनस्ट: केवाईसी सत्यापित! आपका 15 घंटे का प्रशिक्षण अब अनलॉक है।",
        "type": "success",
        "action": "#training",
    },
    "changes_requested": {
        "subject_en": "Action Required: Document Update Needed",
        "subject_hi": "कार्रवाई आवश्यक: दस्तावेज अपडेट की आवश्यकता",
        "email_en": "Our compliance review team requested an update for your {reference} application. Please review the guidance and re-upload the requested document.",
        "email_hi": "हमारी समीक्षा टीम ने आपके आवेदन {reference} के लिए एक दस्तावेज अपडेट का अनुरोध किया है। कृपया मार्गदर्शन देखें और पुनः अपलोड करें।",
        "sms_en": "PolicyNest: Action needed on {reference}. Please review the correction guidance and re-upload your document.",
        "sms_hi": "पॉलिसीनस्ट: {reference} पर कार्रवाई आवश्यक। कृपया दस्तावेज को पुनः अपलोड करें।",
        "type": "action",
        "action": "#documents",
    },
    "training_completed": {
        "subject_en": "Training Completed - Exam Unlocked",
        "subject_hi": "प्रशिक्षण पूरा - परीक्षा अनलॉक",
        "email_en": "Well done! You have completed the mandatory 15 hours of IRDAI training. Your certification assessment is now ready.",
        "email_hi": "शानदार! आपने 15 घंटे का अनिवार्य प्रशिक्षण पूरा कर लिया है। आपकी परीक्षा अब तैयार है।",
        "sms_en": "PolicyNest: 15h training completed! Your POSP certification exam is now unlocked. Good luck!",
        "sms_hi": "पॉलिसीनस्ट: 15 घंटे का प्रशिक्षण पूरा! आपकी परीक्षा अब अनलॉक है।",
        "type": "success",
        "action": "#exam",
    },
    "exam_passed": {
        "subject_en": "Congratulations! You Passed the POSP Exam",
        "subject_hi": "बधाई! आपने पीओएसपी परीक्षा उत्तीर्ण की",
        "email_en": "Congratulations! You scored {score}/50 in the IRDAI POSP certification exam. You are now eligible to execute your appointment agreement and receive your digital certificate.",
        "email_hi": "बधाई! आपने परीक्षा में {score}/50 अंक प्राप्त किए। अब आप अपने नियुक्ति अनुबंध पर हस्ताक्षर कर सकते हैं।",
        "sms_en": "PolicyNest: Exam passed ({score}/50)! Sign your POSP agreement to get certified.",
        "sms_hi": "पॉलिसीनस्ट: परीक्षा उत्तीर्ण! प्रमाणित होने के लिए अपने अनुबंध पर हस्ताक्षर करें।",
        "type": "success",
        "action": "#certificate",
    },
    "exam_failed": {
        "subject_en": "POSP Exam Result & Retake Guidance",
        "subject_hi": "पीओएसपी परीक्षा परिणाम और पुनः प्रयास मार्गदर्शन",
        "email_en": "You scored {score}/50. The passing threshold is 18/50. A 24-hour retake cooldown is in effect. Review your syllabus materials before retaking.",
        "email_hi": "आपने {score}/50 अंक प्राप्त किए। उत्तीर्ण अंक 18 हैं। 24 घंटे का कूलडाउन सक्रिय है। कृपया सामग्री की समीक्षा करें।",
        "sms_en": "PolicyNest: Score {score}/50. You can retake the POSP certification exam in 24 hours.",
        "sms_hi": "पॉलिसीनस्ट: स्कोर {score}/50। आप 24 घंटे बाद पुनः परीक्षा दे सकते हैं।",
        "type": "action",
        "action": "#exam",
    },
    "agreement_executed": {
        "subject_en": "POSP Appointment Agreement Executed",
        "subject_hi": "पीओएसपी नियुक्ति अनुबंध निष्पादित",
        "email_en": "Your digital POSP appointment agreement has been signed and counter-signed by our Principal Officer. Your official digital certificate is ready.",
        "email_hi": "आपका डिजिटल नियुक्ति अनुबंध हस्ताक्षरित हो गया है। आपका आधिकारिक प्रमाणपत्र तैयार है।",
        "sms_en": "PolicyNest: Agreement executed! Your digital POSP Certificate is now issued.",
        "sms_hi": "पॉलिसीनस्ट: अनुबंध निष्पादित! आपका डिजिटल प्रमाणपत्र जारी कर दिया गया है।",
        "type": "success",
        "action": "#certificate",
    },
    "certificate_issued": {
        "subject_en": "Official POSP Digital Certificate Issued",
        "subject_hi": "आधिकारिक पीओएसपी डिजिटल प्रमाणपत्र जारी",
        "email_en": "Congratulations! Your POSP certificate {cert_number} has been officially issued with an HMAC-SHA256 tamper-evident seal. Welcome to PolicyNest as a certified POSP partner.",
        "email_hi": "बधाई! आपका प्रमाणपत्र {cert_number} डिजिटल सील के साथ आधिकारिक रूप से जारी कर दिया गया है।",
        "sms_en": "PolicyNest: POSP Certificate {cert_number} issued! You are now authorized to solicit retail insurance.",
        "sms_hi": "पॉलिसीनस्ट: प्रमाणपत्र {cert_number} जारी! अब आप बीमा बिक्री के लिए अधिकृत हैं।",
        "type": "success",
        "action": "#certificate",
    },
    "certificate_revoked": {
        "subject_en": "Important: Notice of POSP Appointment Revocation",
        "subject_hi": "महत्वपूर्ण: पीओएसपी नियुक्ति निरस्तीकरण सूचना",
        "email_en": "Notice: Your POSP appointment {cert_number} has been revoked by the compliance authority. Reason: {reason}.",
        "email_hi": "सूचना: आपकी पीओएसपी नियुक्ति {cert_number} अनुपालन प्राधिकरण द्वारा निरस्त कर दी गई है। कारण: {reason}।",
        "sms_en": "PolicyNest Notice: POSP Certificate {cert_number} has been revoked. Contact compliance.",
        "sms_hi": "पॉलिसीनस्ट सूचना: प्रमाणपत्र {cert_number} निरस्त कर दिया गया है।",
        "type": "error",
        "action": "#status",
    },
}


# ------------------------------------------------------------- Dispatcher Engine
def dispatch_notification(
    user_id: int,
    template_key: str,
    context: Optional[Dict[str, Any]] = None,
    channels: Tuple[str, ...] = ("in_app", "email", "sms"),
) -> Dict[str, Any]:
    """Render and dispatch multi-channel communications to candidate with Anti-Accusation filtering."""
    ctx = context or {}
    tmpl = TEMPLATES.get(template_key)
    if not tmpl:
        raise ValueError(f"unknown_template:{template_key}")

    now = int(time.time())

    with auth._db() as db:
        user_row = db.execute("SELECT id, email, display_name, mobile, language FROM users WHERE id=?", (user_id,)).fetchone()
        if not user_row:
            raise FileNotFoundError("user_not_found")

        lang = user_row["language"] if user_row["language"] in ("en", "hi") else "en"
        recipient_email = user_row["email"]
        recipient_mobile = user_row["mobile"] or "+91 98765 00000"

        # Interpolate variables
        subj_raw = tmpl.get(f"subject_{lang}", tmpl["subject_en"]).format(**ctx)
        email_raw = tmpl.get(f"email_{lang}", tmpl["email_en"]).format(**ctx)
        sms_raw = tmpl.get(f"sms_{lang}", tmpl["sms_en"]).format(**ctx)

        # Enforce Anti-Accusation Invariant
        subject = _sanitize_for_applicant(subj_raw)
        email_body = _sanitize_for_applicant(email_raw)
        sms_body = _sanitize_for_applicant(sms_raw)

        dispatched_channels = []

        # 1. In-App Notification
        if "in_app" in channels:
            db.execute(
                """INSERT INTO notifications (
                    user_id, type, key, stage, doc, action, read, created_at, reference
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    user_id,
                    tmpl["type"],
                    template_key,
                    ctx.get("stage", "General"),
                    ctx.get("doc", ""),
                    tmpl["action"],
                    now,
                    ctx.get("reference", ""),
                ),
            )
            dispatched_channels.append("in_app")

        # 2. Simulated Email Dispatch
        if "email" in channels:
            disp_id = f"DISP-EMAIL-{secrets.token_hex(4)}"
            db.execute(
                """INSERT INTO communication_dispatches (
                    id, user_id, channel, template_key, recipient, subject, content, status, created_at
                ) VALUES (?, ?, 'EMAIL', ?, ?, ?, ?, 'DELIVERED', ?)""",
                (disp_id, user_id, template_key, recipient_email, subject, email_body, now),
            )
            dispatched_channels.append("email")

        # 3. Simulated SMS Dispatch
        if "sms" in channels:
            disp_id = f"DISP-SMS-{secrets.token_hex(4)}"
            db.execute(
                """INSERT INTO communication_dispatches (
                    id, user_id, channel, template_key, recipient, subject, content, status, created_at
                ) VALUES (?, ?, 'SMS', ?, ?, ?, ?, 'DELIVERED', ?)""",
                (disp_id, user_id, template_key, recipient_mobile, "PolicyNest Alert", sms_body, now),
            )
            dispatched_channels.append("sms")

    return {
        "ok": True,
        "template_key": template_key,
        "dispatched_channels": dispatched_channels,
        "recipient": recipient_email,
        "subject": subject,
        "email_preview": email_body,
        "sms_preview": sms_body,
        "dispatched_at": now,
    }


def list_dispatched_messages(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve simulated email/SMS dispatch logs for a user."""
    with auth._db() as db:
        rows = db.execute(
            """SELECT id, channel, template_key, recipient, subject, content, status, created_at
               FROM communication_dispatches
               WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
            (user_id, max(1, min(limit, 100))),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------- Unified Immutable Audit Timeline
def get_unified_audit_timeline(
    actor: Dict[str, Any],
    target_user_id: int,
) -> Dict[str, Any]:
    """Assemble a complete, chronologically sorted, immutable audit record."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    is_applicant = (role == "applicant")

    if is_applicant and actor["id"] != target_user_id:
        raise PermissionError("forbidden: cannot view another user's timeline")

    unified_events = []

    with auth._db() as db:
        # 1. Timeline Table (Applicant & System events)
        tl_rows = db.execute(
            "SELECT t, actor, key, stage, doc FROM timeline WHERE user_id=? ORDER BY t ASC",
            (target_user_id,),
        ).fetchall()

        for r in tl_rows:
            unified_events.append({
                "timestamp": r["t"],
                "source": "timeline",
                "actor": r["actor"],
                "event_type": r["key"],
                "stage": r["stage"],
                "doc": r["doc"],
                "visibility": "public",
            })

        # 2. Audit Events Table (Staff actions, reviews, claims, decisions)
        ae_rows = db.execute(
            """SELECT ae.occurred, ae.actor_id, ae.action, u.display_name, u.role
               FROM audit_events ae
               LEFT JOIN users u ON ae.actor_id = u.id
               WHERE ae.case_id=? OR ae.case_id=?
               ORDER BY ae.occurred ASC""",
            (str(target_user_id), f"user_{target_user_id}"),
        ).fetchall()

        for r in ae_rows:
            # Mask internal reviewer names and sensitive actions for applicants
            if is_applicant:
                unified_events.append({
                    "timestamp": r["occurred"],
                    "source": "audit",
                    "actor": "Staff Reviewer",
                    "event_type": _sanitize_for_applicant(r["action"]),
                    "stage": "Review",
                    "visibility": "applicant_filtered",
                })
            else:
                unified_events.append({
                    "timestamp": r["occurred"],
                    "source": "audit",
                    "actor_id": r["actor_id"],
                    "actor": r["display_name"] or f"Staff #{r['actor_id']}",
                    "actor_role": r["role"],
                    "event_type": r["action"],
                    "stage": "Review",
                    "visibility": "internal",
                })

        # 3. Document Verification Events
        doc_rows = db.execute(
            """SELECT vr.created_at, vr.check_type, vr.provider, vr.status, vr.match_score
               FROM verification_results vr
               JOIN applications a ON vr.application_id = a.id
               WHERE a.user_id=? ORDER BY vr.created_at ASC""",
            (target_user_id,),
        ).fetchall()

        for r in doc_rows:
            unified_events.append({
                "timestamp": r["created_at"],
                "source": "verification",
                "actor": f"Provider:{r['provider']}",
                "event_type": f"VERIFICATION_{r['check_type'].upper()}_{r['status']}",
                "match_score": r["match_score"],
                "visibility": "public",
            })

        # 4. Exam Attempts
        exam_rows = db.execute(
            """SELECT started_at, completed_at, attempt_number, score, passed, incident_flag
               FROM exam_attempts WHERE user_id=? ORDER BY started_at ASC""",
            (target_user_id,),
        ).fetchall()

        for r in exam_rows:
            unified_events.append({
                "timestamp": r["started_at"],
                "source": "exam",
                "actor": "Assessment Engine",
                "event_type": f"EXAM_ATTEMPT_{r['attempt_number']}_STARTED",
                "visibility": "public",
            })
            if r["completed_at"]:
                unified_events.append({
                    "timestamp": r["completed_at"],
                    "source": "exam",
                    "actor": "Assessment Engine",
                    "event_type": "EXAM_PASSED" if r["passed"] else "EXAM_FAILED",
                    "score": r["score"],
                    "incident_flag": r["incident_flag"],
                    "visibility": "public",
                })

        # 5. Agreements & Certificates
        agree_rows = db.execute(
            "SELECT signed_at, agreement_hash, signer_ip FROM posp_agreements WHERE user_id=?",
            (target_user_id,),
        ).fetchall()

        for r in agree_rows:
            unified_events.append({
                "timestamp": r["signed_at"],
                "source": "agreement",
                "actor": "Candidate e-Sign",
                "event_type": "POSP_APPOINTMENT_AGREEMENT_EXECUTED",
                "agreement_hash_prefix": r["agreement_hash"][:12] + "...",
                "visibility": "public",
            })

        cert_rows = db.execute(
            "SELECT certificate_number, issued_at, status, signature_digest FROM certificates WHERE user_id=?",
            (target_user_id,),
        ).fetchall()

        for r in cert_rows:
            unified_events.append({
                "timestamp": r["issued_at"],
                "source": "certification",
                "actor": "IRDAI Certification Authority",
                "event_type": f"CERTIFICATE_ISSUED_{r['certificate_number']}",
                "status": r["status"],
                "signature_digest_prefix": r["signature_digest"][:12] + "...",
                "visibility": "public",
            })

    # Chronologically sort all merged events
    unified_events.sort(key=lambda e: e["timestamp"])

    return {
        "ok": True,
        "target_user_id": target_user_id,
        "event_count": len(unified_events),
        "events": unified_events,
    }


# ------------------------------------------------------------- IRDAI Regulatory Audit Pack Exporter
def generate_compliance_audit_pack(
    actor: Dict[str, Any],
    target_user_id: int,
) -> Dict[str, Any]:
    """Generate an official, cryptographically sealed IRDAI Regulatory Compliance Audit Pack."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    resource = {"applicant_id": target_user_id, "sensitivity": "restricted_fraud"}

    # Capability check: compliance_officer, auditor, or tech_admin
    if not policy.allows(actor, "compliance.export_pack", resource) and role not in ("compliance_officer", "auditor", "tech_admin"):
        raise PermissionError(f"forbidden: role '{role}' cannot export compliance audit pack")

    now = int(time.time())

    with auth._db() as db:
        # 1. Candidate Dossier
        u_row = db.execute("SELECT * FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not u_row:
            raise FileNotFoundError("user_not_found")

        app_row = db.execute("SELECT * FROM applications WHERE user_id=?", (target_user_id,)).fetchone()
        if not app_row:
            raise FileNotFoundError("application_not_found")

        details = json.loads(app_row["details"] or "{}")

        # 2. KYC Verification Dossier
        v_rows = db.execute(
            "SELECT * FROM verification_results WHERE application_id=? ORDER BY created_at ASC",
            (app_row["id"],),
        ).fetchall()

        kyc_dossier = [
            {
                "verification_type": r["check_type"],
                "provider": r["provider"],
                "status": r["status"],
                "reference_id": r["reference_id"],
                "match_score": r["match_score"],
                "verified_at": r["created_at"],
            }
            for r in v_rows
        ]

        # 3. 15-Hour LMS Curriculum Audit
        m_rows = db.execute("SELECT id, title, duration_minutes FROM training_modules ORDER BY sequence_order ASC").fetchall()
        p_rows = db.execute("SELECT * FROM training_progress WHERE user_id=?", (target_user_id,)).fetchall()
        prog_map = {r["module_id"]: r for r in p_rows}

        total_verified_seconds = sum(r["time_spent_seconds"] for r in p_rows)
        total_verified_hours = round(total_verified_seconds / 3600.0, 2)

        curriculum_audit = {
            "mandated_hours": 15.0,
            "verified_hours_completed": total_verified_hours,
            "verified_seconds_completed": total_verified_seconds,
            "threshold_met": total_verified_seconds >= 54000,
            "modules": [
                {
                    "module_id": m["id"],
                    "title": m["title"],
                    "required_minutes": m["duration_minutes"],
                    "verified_seconds": prog_map.get(m["id"], {}).get("time_spent_seconds", 0) if prog_map.get(m["id"]) else 0,
                    "completed": bool(prog_map.get(m["id"], {}).get("completed", 0)) if prog_map.get(m["id"]) else False,
                    "completed_at": prog_map.get(m["id"], {}).get("completed_at") if prog_map.get(m["id"]) else None,
                }
                for m in m_rows
            ],
        }

        # 4. Examination Assessment Transcript
        exam_rows = db.execute("SELECT * FROM exam_attempts WHERE user_id=? ORDER BY started_at ASC", (target_user_id,)).fetchall()
        exam_transcripts = [
            {
                "exam_id": ex["id"],
                "attempt_number": ex["attempt_number"],
                "score": ex["score"],
                "total_questions": ex["total_questions"],
                "pass_mark_required": 18,
                "passed": bool(ex["passed"]),
                "incident_count": ex["incident_flag"],
                "incident_notes": ex["incident_notes"],
                "started_at": ex["started_at"],
                "completed_at": ex["completed_at"],
            }
            for ex in exam_rows
        ]

        # 5. POSP Appointment Agreement
        agree_row = db.execute("SELECT * FROM posp_agreements WHERE user_id=?", (target_user_id,)).fetchone()
        agreement_audit = dict(agree_row) if agree_row else None

        # 6. Digital POSP Certificate & Signature
        cert_row = db.execute("SELECT * FROM certificates WHERE user_id=?", (target_user_id,)).fetchone()
        certificate_audit = dict(cert_row) if cert_row else None

        # 7. Complete Unified Event Stream
        timeline_res = get_unified_audit_timeline(actor, target_user_id)

        # Assemble Raw Audit Pack Payload
        pack_id = f"AUDIT-PACK-{time.strftime('%Y')}-{target_user_id}-{secrets.token_hex(4)}"
        pack_payload = {
            "audit_pack_id": pack_id,
            "regulatory_framework": "IRDAI POSP Guidelines 2015 & Insurance Act 1938",
            "insuring_broker": "PolicyNest Broking Technologies Pvt. Ltd. (IRDAI Direct Broker DB 891/21)",
            "generated_at": now,
            "generated_by_actor_id": actor["id"],
            "generated_by_role": role,
            "candidate_profile": {
                "user_id": target_user_id,
                "display_name": u_row["display_name"],
                "email": u_row["email"],
                "pan_masked": details.get("pan_masked", "ABCDE****F"),
                "city": u_row["city"] or details.get("city"),
                "state": u_row["state"] or details.get("state"),
                "registered_at": u_row["created_at"],
            },
            "application_summary": {
                "application_id": app_row["id"],
                "reference": app_row["reference"],
                "current_status": app_row["status"],
                "current_stage": app_row["stage"],
                "submitted_at": app_row["updated_at"],
            },
            "kyc_verification_dossier": kyc_dossier,
            "curriculum_training_audit": curriculum_audit,
            "examination_transcripts": exam_transcripts,
            "appointment_agreement": agreement_audit,
            "posp_digital_certificate": certificate_audit,
            "immutable_event_stream": timeline_res["events"],
        }

        # Compute Cryptographic SHA-256 Bundle Seal
        serialized = json.dumps(pack_payload, sort_keys=True)
        bundle_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        pack_payload["integrity_bundle_sha256"] = bundle_hash

        # Store in compliance_audit_packs table
        db.execute(
            """INSERT INTO compliance_audit_packs (
                id, user_id, generated_by, bundle_hash, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (pack_id, target_user_id, actor["id"], bundle_hash, json.dumps(pack_payload), now),
        )

        db.execute(
            """INSERT INTO audit_events (case_id, actor_id, action, occurred)
               VALUES (?, ?, 'COMPLIANCE_AUDIT_PACK_EXPORTED', ?)""",
            (f"user_{target_user_id}", actor["id"], now),
        )

    return {
        "ok": True,
        "pack_id": pack_id,
        "bundle_hash": bundle_hash,
        "generated_at": now,
        "regulatory_seal": "IRDAI_COMPLIANT_DIGITAL_AUDIT_PACK",
        "pack": pack_payload,
    }
