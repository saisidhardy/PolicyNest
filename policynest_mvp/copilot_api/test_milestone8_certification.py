"""Milestone 8 Verification Suite: Digital POSP Certification & Public Verification.

Tests:
1. Eligibility verification: status-gated pre-requisites (KYC, 15h Training, Exam Passed).
2. POSP Appointment Agreement: bilingual legal clauses, Section 41 Anti-Rebating undertaking.
3. Digital Agreement execution: Aadhaar e-Sign simulation, cryptographic agreement hash.
4. Tamper-evident POSP certificate issuance:
   - Unique POSP code (PN-POSP-YYYY-XXXXX).
   - HMAC-SHA256 signature digest over critical fields.
   - State transition to CERTIFIED and stage to Certified.
5. Cryptographic tamper detection: modified payload invalidates signature.
6. Zero-Auth public verification registry:
   - Active certificate verification.
   - Non-existent certificate handling.
   - Tampered certificate handling.
7. Certificate Administrator lifecycle:
   - Admin list and filtering.
   - Admin revocation with disciplinary reason and audit log.
   - Verification of revoked status in public registry.
8. Official SVG certificate rendering.
9. ABAC security invariants across applicant, reviewer, and certificate_admin roles.
"""
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import application
import auth
import certification
import migrations
import policy
import portal


class Milestone8CertificationTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m8.sqlite3"
        self.orig_db_env = os.environ.get("POLICYNEST_DB_PATH")
        self.orig_jwt_env = os.environ.get("JWT_SECRET")
        os.environ["POLICYNEST_DB_PATH"] = str(self.db_path)
        os.environ["JWT_SECRET"] = "x" * 32

        auth.DB_PATH = self.db_path
        auth.init_db()
        portal.init()
        with auth._db() as db:
            migrations.run_migrations(db)

        # Provision Staff personas
        admin_actor = {"id": 1, "role": "tech_admin"}
        self.cert_admin = auth.provision_staff(
            admin_actor, "cert.admin@test.com", "certificate_admin",
            temp_password="Password1234#", display_name="Certificate Admin"
        )
        self.reviewer = auth.provision_staff(
            admin_actor, "rev@test.com", "reviewer",
            temp_password="Password1234#", display_name="Standard Reviewer"
        )

        # Register test applicants
        self.applicant_1 = auth.register("app1@test.com", "SecurePass123#", "Asha Sharma")
        self.applicant_2 = auth.register("app2@test.com", "SecurePass123#", "Vikram Malhotra")

    def tearDown(self):
        if self.orig_db_env:
            os.environ["POLICYNEST_DB_PATH"] = self.orig_db_env
            auth.DB_PATH = Path(self.orig_db_env)
        elif "POLICYNEST_DB_PATH" in os.environ:
            del os.environ["POLICYNEST_DB_PATH"]

        if self.orig_jwt_env:
            os.environ["JWT_SECRET"] = self.orig_jwt_env
        elif "JWT_SECRET" in os.environ:
            del os.environ["JWT_SECRET"]

        self.temp_dir.cleanup()

    # 1. Eligibility Verification
    def test_certificate_eligibility_gating(self):
        app = application.get_or_create_application(self.applicant_1)

        # In DRAFT: ineligible
        el_draft = certification.get_certificate_eligibility(self.applicant_1)
        self.assertFalse(el_draft["eligible"])
        self.assertEqual(el_draft["reason"], "EXAM_NOT_PASSED")

        # In TRAINING_COMPLETE: ineligible
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        el_training = certification.get_certificate_eligibility(self.applicant_1)
        self.assertFalse(el_training["eligible"])

        # In EXAM_PASSED: eligible to execute agreement
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED', stage='Certificate' WHERE id=?", (app["id"],))

        el_ready = certification.get_certificate_eligibility(self.applicant_1)
        self.assertTrue(el_ready["eligible"])
        self.assertFalse(el_ready["agreement_completed"])
        self.assertTrue(el_ready["can_execute_agreement"])

    # 2. Agreement Template Retrieval (EN & HI)
    def test_posp_agreement_template_bilingual(self):
        tmpl_en = certification.get_posp_agreement_template(self.applicant_1, lang="en")
        self.assertTrue(tmpl_en["ok"])
        self.assertEqual(tmpl_en["agreement_type"], "IRDAI_POSP_APPOINTMENT_AGREEMENT")
        self.assertIn("Asha Sharma", tmpl_en["candidate_name"])
        self.assertGreaterEqual(len(tmpl_en["clauses"]), 5)
        # Check Section 41 presence
        has_sec41 = any("Section 41" in c["clause"] or "Section 41" in c["text"] for c in tmpl_en["clauses"])
        self.assertTrue(has_sec41)

        # Hindi version
        tmpl_hi = certification.get_posp_agreement_template(self.applicant_1, lang="hi")
        self.assertTrue(tmpl_hi["ok"])
        self.assertIn("धारा 41", tmpl_hi["clauses"][3]["clause"])

    # 3. Digital Agreement Execution
    def test_posp_agreement_execution(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        agree_res = certification.execute_posp_agreement(
            self.applicant_1,
            declaration_accepted=True,
            client_ip="203.0.113.195",
        )
        self.assertTrue(agree_res["ok"])
        self.assertIn("AGREE-", agree_res["agreement_id"])
        self.assertEqual(agree_res["status"], "AGREEMENT_EXECUTED")
        self.assertTrue(agree_res["agreement_hash"])

        # Verify application status transitioned
        with auth._db() as db:
            app_row = db.execute("SELECT status FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "AGREEMENT_EXECUTED")

            # Verify recorded in agreements table
            rec = db.execute("SELECT * FROM posp_agreements WHERE user_id=?", (self.applicant_1["id"],)).fetchone()
            self.assertIsNotNone(rec)
            self.assertEqual(rec["signer_name"], "Asha Sharma")
            self.assertEqual(rec["signer_ip"], "203.0.113.195")

    # 4. Tamper-Evident POSP Certificate Issuance
    def test_certificate_issuance_and_state_transition(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        # Execute agreement first
        certification.execute_posp_agreement(self.applicant_1)

        # Issue certificate
        cert_res = certification.issue_posp_certificate(self.applicant_1)
        self.assertTrue(cert_res["ok"])
        self.assertIn("PN-POSP-", cert_res["certificate_number"])
        self.assertEqual(cert_res["holder_name"], "Asha Sharma")
        self.assertEqual(cert_res["status"], "ACTIVE")
        self.assertTrue(cert_res["signature_valid"])
        self.assertIn("Life", cert_res["lines_of_business"])
        self.assertIn("General", cert_res["lines_of_business"])
        self.assertIn("Health", cert_res["lines_of_business"])

        # Verify application state transitioned to CERTIFIED
        with auth._db() as db:
            app_row = db.execute("SELECT status, stage FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "CERTIFIED")
            self.assertEqual(app_row[1], "Certified")

            # Check timeline event
            tl = db.execute("SELECT key FROM timeline WHERE user_id=? AND key='certificate_issued'", (self.applicant_1["id"],)).fetchone()
            self.assertIsNotNone(tl)

            # Check notification
            notif = db.execute("SELECT key FROM notifications WHERE user_id=? AND key='certificate_issued'", (self.applicant_1["id"],)).fetchone()
            self.assertIsNotNone(notif)

    # 5. Cryptographic Tamper Detection
    def test_cryptographic_tamper_detection(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        certification.execute_posp_agreement(self.applicant_1)
        cert_res = certification.issue_posp_certificate(self.applicant_1)
        cert_number = cert_res["certificate_number"]

        # Valid initially
        pub_valid = certification.verify_certificate_public(cert_number)
        self.assertTrue(pub_valid["verified"])
        self.assertEqual(pub_valid["tamper_check"], "VALID")

        # Maliciously modify holder_name in database without updating HMAC signature
        with auth._db() as db:
            db.execute("UPDATE certificates SET posp_name='Impostor Name' WHERE certificate_number=?", (cert_number,))

        # Verification must detect tampering!
        pub_tampered = certification.verify_certificate_public(cert_number)
        self.assertFalse(pub_tampered["verified"])
        self.assertEqual(pub_tampered["status"], "TAMPERED")

    # 6. Zero-Auth Public Verification Registry
    def test_zero_auth_public_verification(self):
        app = application.get_or_create_application(self.applicant_2)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        certification.execute_posp_agreement(self.applicant_2)
        cert = certification.issue_posp_certificate(self.applicant_2)
        cert_no = cert["certificate_number"]
        cert_id = cert["id"]

        # Lookup by certificate_number
        res1 = certification.verify_certificate_public(cert_no)
        self.assertTrue(res1["verified"])
        self.assertEqual(res1["holder_name"], "Vikram Malhotra")
        self.assertEqual(res1["status"], "ACTIVE")

        # Lookup by certificate_id
        res2 = certification.verify_certificate_public(cert_id)
        self.assertTrue(res2["verified"])
        self.assertEqual(res2["certificate_number"], cert_no)

        # Lookup non-existent
        res_fake = certification.verify_certificate_public("PN-POSP-9999-99999")
        self.assertFalse(res_fake["verified"])
        self.assertEqual(res_fake["status"], "NOT_FOUND")

    # 7. Certificate Administrator Lifecycle & Revocation
    def test_admin_certificate_management_and_revocation(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        certification.execute_posp_agreement(self.applicant_1)
        cert = certification.issue_posp_certificate(self.applicant_1)
        cert_no = cert["certificate_number"]

        # Admin lists certificates
        certs = certification.admin_list_certificates(self.cert_admin)
        self.assertGreaterEqual(len(certs), 1)

        # Admin revokes certificate for disciplinary reasons
        rev_res = certification.admin_revoke_certificate(
            self.cert_admin,
            cert_no,
            reason="Violation of Single Affiliation Under IRDAI Guidelines",
        )
        self.assertTrue(rev_res["ok"])
        self.assertEqual(rev_res["status"], "REVOKED")

        # Public lookup must now reflect revoked status
        pub_rev = certification.verify_certificate_public(cert_no)
        self.assertTrue(pub_rev["verified"])
        self.assertEqual(pub_rev["status"], "REVOKED")
        self.assertIn("Single Affiliation", pub_rev["revocation_reason"])

    # 8. SVG Certificate Rendering
    def test_svg_certificate_rendering(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED' WHERE id=?", (app["id"],))

        certification.execute_posp_agreement(self.applicant_1)
        cert = certification.issue_posp_certificate(self.applicant_1)

        svg = certification.render_certificate_svg(cert)
        self.assertIn("<svg", svg)
        self.assertIn("Asha Sharma", svg)
        self.assertIn(cert["certificate_number"], svg)
        self.assertIn("Certificate of Appointment", svg)
        self.assertIn("IRDAI", svg)

    # 9. ABAC Security Invariants
    def test_certification_abac_security_invariants(self):
        # Applicant cannot call admin endpoints
        with self.assertRaises(PermissionError):
            certification.admin_list_certificates(self.applicant_1)

        with self.assertRaises(PermissionError):
            certification.admin_revoke_certificate(self.applicant_1, "PN-POSP-001", "unauthorized")

        # Reviewer cannot revoke certificate
        with self.assertRaises(PermissionError):
            certification.admin_revoke_certificate(self.reviewer, "PN-POSP-001", "unauthorized")


if __name__ == "__main__":
    unittest.main()
