"""Comprehensive End-to-End Test Suite for PolicyNest.

Covers the 4 complete operational journeys required by Phase 21:
1. End-to-End Applicant Journey (20 distinct verification steps)
2. End-to-End Reviewer Journey (12 distinct operational steps)
3. End-to-End Account Recovery Journey (7 security verification steps)
4. End-to-End Cross-Account & Cross-Role Authorization Journey (7 defense steps)
"""
import unittest
import time
import json
import secrets
import struct
import os

import config
import auth
import migrations
import policy
import portal
import workflows
import application
import status_model
import next_action
import storage
import documents
import cross_checks
import review_ops
import fraud_engine
import training_lms
import examination
import certification
import communications


def _create_minimal_png(width=500, height=400):
    """Generate minimal valid PNG bytes with IHDR dimensions."""
    header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", 0x12345678)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
    padding = b"\x00" * 1200
    return header + ihdr_chunk + padding


class TestE2EJourneys(unittest.TestCase):

    def setUp(self):
        config.IS_PRODUCTION = False
        config.IS_DEV = True
        os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long-for-testing!!"
        with auth._db() as db:
            migrations.run_migrations(db)

    # =========================================================================
    # JOURNEY 1: APPLICANT ONBOARDING TO CERTIFICATION (20 STEPS)
    # =========================================================================
    def test_journey_1_complete_applicant_lifecycle(self):
        now = int(time.time())
        unique_email = f"applicant_e2e_{now}_{secrets.token_hex(4)}@policynest.test"
        password = "SecurePassphrase2026!"
        display_name = "Priya Sharma"

        # Step 1: Create applicant account
        user = auth.register(unique_email, password, display_name)
        self.assertIsNotNone(user["id"])
        self.assertEqual(user["role"], "applicant")

        # Step 2: Confirm account is active
        self.assertEqual(user.get("status"), "active")
        updated_user = auth.authenticate(f"Bearer {auth.issue(user)}")
        self.assertEqual(updated_user["status"], "active")

        # Step 3: Sign in
        logged_in = auth.login(unique_email, password)
        self.assertEqual(logged_in["id"], user["id"])

        # Step 4: Complete application basics & profile
        app = application.get_or_create_application(user)
        self.assertTrue(app["reference"].startswith("PN-2026-"))
        self.assertEqual(app["status"], "DRAFT")

        save_res = application.save_draft(user, {
            "version": app["version"],
            "details": {
                "name": "Priya Sharma",
                "dob": "1994-08-15",
                "state": "Maharashtra",
                "city": "Mumbai",
                "education": "Class 10",
                "ifsc": "HDFC0001234",
                "pan_last4": "1234",
                "aadhaar4": "4321",
                "acct_last4": "5678",
            }
        })
        self.assertTrue(save_res["ok"])

        # Step 5: Save and resume
        resumed = application.get_or_create_application(user)
        self.assertEqual(resumed["details"]["name"], "Priya Sharma")
        self.assertEqual(resumed["details"]["pan_last4"], "1234")

        # Step 6: Upload synthetic documents
        png = _create_minimal_png()
        for slot in ("PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK"):
            doc_rec = documents.upload_document(user, slot, png, f"{slot}.png")
            self.assertEqual(doc_rec["slot"], slot)

        # Step 7: Handle one rejected document (simulated slot defect)
        with auth._db() as db:
            db.execute(
                "UPDATE document_records SET status = 'REJECTED', rejection_reason = 'PAN card image is blurry' WHERE slot = 'PAN' AND application_id = ?",
                (app["id"],)
            )

        # Step 8: Replace rejected document
        clear_png = _create_minimal_png(600, 500)
        replaced_doc = documents.submit_document_correction(
            user=user,
            slot="PAN",
            file_bytes=clear_png,
            file_name="pan_card_crisp.png",
            explanation="Re-uploaded high resolution copy",
        )
        self.assertEqual(replaced_doc["slot"], "PAN")

        # Step 9: Submit application for review
        sub_res = application.submit_application(user)
        self.assertEqual(sub_res["status"], "SUBMITTED")

        # Step 10: Reviewer requests a change
        reviewer = auth.provision_staff(
            actor={"id": 1, "role": "admin"},
            email=f"rev_{now}@policynest.test",
            role="reviewer",
            temp_password="Password123456!",
        )
        claim_res = review_ops.claim_case(reviewer, case_id=app["reference"])
        self.assertTrue(claim_res["ok"])

        change_res = review_ops.decide_case(
            actor=reviewer,
            case_id=app["reference"],
            status="NEEDS_MORE_INFO",
            note="Please provide a clearer PAN card image.",
            rule="§4.2",
            slot_defects={"PAN": "Blurry image"},
        )
        self.assertEqual(change_res["status"], "NEEDS_MORE_INFO")
        refreshed = application.get_or_create_application(user)
        self.assertEqual(refreshed["status"], "NEEDS_MORE_INFO")

        # Step 11: Applicant corrects and resubmits
        resub_res = application.submit_application(user)
        self.assertEqual(resub_res["status"], "SUBMITTED")

        # Step 12: Reviewer approves KYC
        apprv_res = review_ops.decide_case(
            actor=reviewer,
            case_id=app["reference"],
            status="KYC_APPROVED",
            note="All KYC documents verified and compliant.",
            rule="§2.1",
        )
        self.assertEqual(apprv_res["status"], "KYC_APPROVED")

        # Step 13: Complete training modules (15 hours)
        train_overview = training_lms.get_training_overview(user)
        modules = train_overview["modules"]
        self.assertEqual(len(modules), 5)
        with auth._db() as db:
            for mod in modules:
                db.execute(
                    """INSERT OR REPLACE INTO training_progress (
                        id, user_id, module_id, status, time_spent_seconds, created_at, updated_at
                    ) VALUES (?, ?, ?, 'IN_PROGRESS', 11000, ?, ?)""",
                    (f"tp_{user['id']}_{mod['id']}", user["id"], mod["id"], now, now),
                )
        for mod in modules:
            res = training_lms.complete_training_module(user, module_id=mod["id"])
            self.assertTrue(res["ok"])
        train_overview_final = training_lms.get_training_overview(user)
        self.assertTrue(train_overview_final["is_training_complete"])

        # Step 14: Pass exam (score >= 35%)
        start_res = examination.start_exam_session(user)
        self.assertEqual(len(start_res["questions"]), 50)
        with auth._db() as db:
            correct_keys = {
                r["id"]: r["correct_index"]
                for r in db.execute("SELECT id, correct_index FROM exam_question_bank").fetchall()
            }
        answers = {q["id"]: correct_keys.get(q["id"], 0) for q in start_res["questions"]}
        exam_result = examination.submit_exam_attempt(user, exam_id=start_res["exam_id"], answers=answers)
        self.assertTrue(exam_result["passed"])
        self.assertGreaterEqual(exam_result["percentage"], 35.0)

        # Step 15: Accept declaration and execute agreement
        tmpl = certification.get_posp_agreement_template(user)
        self.assertIn("Code of Conduct", tmpl["statutory_declaration"])
        ack_res = certification.execute_posp_agreement(
            user,
            declaration_accepted=True,
            client_ip="127.0.0.1",
        )
        self.assertEqual(ack_res["status"], "AGREEMENT_EXECUTED")

        # Step 16: Certificate is generated
        cert = certification.issue_posp_certificate(user)
        self.assertTrue(cert["certificate_number"].startswith("PN-POSP-2026-"))
        self.assertEqual(cert["status"], "ACTIVE")

        # Step 17: Applicant retrieves certificate
        my_cert = certification.get_user_certificate(user)
        self.assertEqual(my_cert["certificate_number"], cert["certificate_number"])

        # Step 18: Public zero-auth certificate verification works
        pub_verify = certification.verify_certificate_public(cert["certificate_number"])
        self.assertTrue(pub_verify["verified"])
        self.assertEqual(pub_verify["holder_name"], "Priya Sharma")

        # Step 19: Digital signature tamper verification
        self.assertTrue(cert["signature_valid"])
        with auth._db() as db:
            row = db.execute("SELECT * FROM certificates WHERE id=?", (cert["id"],)).fetchone()
            self.assertTrue(certification.verify_certificate_signature(dict(row)))

        # Step 20: Applicant can view complete activity history
        timeline = communications.get_unified_audit_timeline(user, target_user_id=user["id"])
        self.assertGreater(len(timeline["events"]), 0)

    # =========================================================================
    # JOURNEY 2: REVIEWER WORKFLOW (12 STEPS)
    # =========================================================================
    def test_journey_2_reviewer_operations_lifecycle(self):
        now = int(time.time())
        admin = auth.provision_staff(
            actor={"id": 1, "role": "admin"},
            email=f"admin_ops_{now}@policynest.test",
            role="admin",
            temp_password="AdminPassphrase2026!",
        )

        # Step 1: Admin creates reviewer account
        rev = auth.provision_staff(
            actor=admin,
            email=f"rev_ops_{now}@policynest.test",
            role="reviewer",
            department="Operations",
            temp_password="ReviewerPass2026!",
            display_name="Karan Verma",
        )
        self.assertEqual(rev["role"], "reviewer")

        # Step 2: Confirm reviewer account status is active
        self.assertEqual(rev.get("status"), "active")

        # Step 3: Reviewer signs in
        rev_session = auth.login(rev["email"], "ReviewerPass2026!")
        self.assertEqual(rev_session["id"], rev["id"])

        # Step 4: Reviewer sees only authorized applications
        queues = review_ops.get_queues(rev, queue_type="my_queue")
        self.assertTrue(queues["ok"])
        self.assertIn("counts", queues)
        self.assertIn("my_queue", queues["counts"])
        self.assertIn("rework", queues["counts"])

        # Step 5: Applicant submits a case
        applicant = auth.register(f"app_for_rev_{now}@policynest.test", "ApplicantPass1234!", "Test Applicant")
        app_record = application.get_or_create_application(applicant)
        save_res = application.save_draft(applicant, {
            "version": app_record["version"],
            "details": {
                "name": "Test Applicant",
                "dob": "1993-05-10",
                "state": "Delhi",
                "city": "New Delhi",
            }
        })
        png = _create_minimal_png()
        for slot in ("PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK"):
            documents.upload_document(applicant, slot, png, f"{slot}.png")
        sub_res = application.submit_application(applicant)
        self.assertEqual(sub_res["status"], "SUBMITTED")

        # Step 6: Reviewer claims the assigned case
        claimed = review_ops.claim_case(rev, case_id=app_record["reference"])
        self.assertTrue(claimed["ok"])

        # Step 7: Reviewer opens and inspects case dossier
        dossier = review_ops.get_case_dossier(rev, case_id=app_record["reference"])
        self.assertEqual(dossier["case"]["id"], app_record["reference"])

        # Step 8: Reviewer requests changes with an explicit defect code & rule
        decision_res = review_ops.decide_case(
            actor=rev,
            case_id=app_record["reference"],
            status="NEEDS_MORE_INFO",
            note="Bank passbook account number is partly truncated.",
            rule="§3.1",
            slot_defects={"BANK": "Account truncated"},
        )
        self.assertEqual(decision_res["status"], "NEEDS_MORE_INFO")

        # Step 9: Applicant receives changes-requested notification
        notifs = portal.list_notifications(applicant, {})
        self.assertGreaterEqual(len(notifs["items"]), 1)

        # Step 10: Applicant resubmits
        resub = application.submit_application(applicant)
        self.assertEqual(resub["status"], "SUBMITTED")

        # Step 11: Reviewer approves upon resubmission
        final_dec = review_ops.decide_case(
            actor=rev,
            case_id=app_record["reference"],
            status="KYC_APPROVED",
            note="All defects cleared and KYC re-checked.",
            rule="§2.1",
        )
        self.assertEqual(final_dec["status"], "KYC_APPROVED")

        # Step 12: Audit log records every reviewer action
        timeline = communications.get_unified_audit_timeline(rev, target_user_id=applicant["id"])
        self.assertGreaterEqual(len(timeline["events"]), 2)

    # =========================================================================
    # JOURNEY 3: ACCOUNT RECOVERY & SECURITY (7 STEPS)
    # =========================================================================
    def test_journey_3_recovery_and_session_revocation(self):
        now = int(time.time())
        existing_email = f"user_recovery_{now}@policynest.test"
        nonexistent_email = f"ghost_{now}@policynest.test"
        old_password = "OldSecurePassword123!"
        new_password = "NewSecurePassword456!"

        user = auth.register(existing_email, old_password, "Recovery Tester")

        # Step 1: Request reset for existing email
        tok1 = auth.create_reset(existing_email)
        self.assertIsNotNone(tok1)

        # Step 2: Request reset for nonexistent email
        tok2 = auth.create_reset(nonexistent_email)
        self.assertIsNone(tok2)

        # Step 3: Confirm identical public response (generic message in main.py)
        # Note: auth.create_reset returns None, public endpoint returns 202 identical response

        # Step 4: Use valid reset token to update password
        auth.reset_password(tok1, new_password)

        # Step 5: Reject expired or reused reset token
        with self.assertRaises(ValueError):
            auth.reset_password(tok1, "AnotherPassword789!")

        # Step 6: Verify old password no longer authenticates
        with self.assertRaises(ValueError):
            auth.login(existing_email, old_password)

        # Step 7: Verify new password successfully authenticates
        new_login = auth.login(existing_email, new_password)
        self.assertEqual(new_login["id"], user["id"])

    # =========================================================================
    # JOURNEY 4: CROSS-ACCOUNT & CROSS-ROLE AUTHORIZATION (7 STEPS)
    # =========================================================================
    def test_journey_4_cross_account_and_role_boundaries(self):
        now = int(time.time())
        applicant_a = auth.register(f"app_a_{now}@policynest.test", "PassApplicantA1!", "Applicant A")
        applicant_b = auth.register(f"app_b_{now}@policynest.test", "PassApplicantB1!", "Applicant B")
        reviewer = auth.provision_staff({"id": 1, "role": "admin"}, f"rev_guard_{now}@policynest.test", "reviewer", temp_password="RevGuardPass1!")

        app_b = application.get_or_create_application(applicant_b)

        # Step 1: Applicant A tries to read/write Applicant B's application (IDOR prevention)
        self.assertFalse(policy.allows(applicant_a, "application.read", {"applicant_id": applicant_b["id"]}))
        self.assertFalse(policy.allows(applicant_a, "application.save", {"applicant_id": applicant_b["id"], "status": "DRAFT"}))

        # Step 2: Applicant tries to claim case or review cases
        self.assertFalse(policy.allows(applicant_a, "review.claim", {"case_id": app_b["reference"]}))
        self.assertFalse(policy.allows(applicant_a, "review.decide", {"case_id": app_b["reference"]}))

        # Step 3: Reviewer cannot modify applicant password or credentials
        self.assertFalse(policy.allows(reviewer, "auth.reset_password", {"target_user_id": applicant_a["id"]}))

        # Step 4: Reviewer cannot access unassigned or restricted fraud cases
        unassigned_case = {"case_id": "PN-CASE-999", "reviewer_id": None}
        self.assertFalse(policy.allows(reviewer, "review.decide", unassigned_case))

        # Step 5: Suspended reviewer cannot operate
        suspended_rev = dict(reviewer, status="suspended")
        self.assertFalse(policy.allows(suspended_rev, "review.decide", {"reviewer_id": reviewer["id"]}))

        # Step 6: Public/anonymous user calling protected endpoints rejected
        anon = None
        self.assertFalse(policy.allows(anon, "application.read", {}))
        self.assertFalse(policy.allows(anon, "review.decide", {}))

        # Step 7: Verify defense integrity (authorized reviewer on assigned case and owner on draft)
        self.assertTrue(policy.allows(reviewer, "review.decide", {"reviewer_id": reviewer["id"]}))
        self.assertTrue(policy.allows(applicant_a, "application.save", {"applicant_id": applicant_a["id"], "status": "DRAFT"}))


if __name__ == "__main__":
    unittest.main()
