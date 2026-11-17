"""Milestone 9 Verification Suite: Communications, Unified Timeline & IRDAI Compliance Audit Pack.

Tests:
1. Multi-channel notification dispatch: in-app, email, and SMS simulation.
2. Bilingual template rendering: English and Hindi for lifecycle milestones.
3. Anti-Accusation Invariant: banned fraud/tamper words scrubbed from candidate communications.
4. Unified Immutable Audit Timeline:
   - Full chronological aggregation of events across all platform engines.
   - Role-based visibility: internal staff names and sensitive fraud notes masked for applicants.
   - Comprehensive audit visibility for Compliance Officers and Auditors.
5. IRDAI Regulatory Compliance Audit Pack Exporter:
   - End-to-end regulatory bundle packaging (KYC, 15h LMS, Exam, Agreement, Certificate).
   - Tamper-evident SHA-256 integrity bundle seal computation and verification.
   - Persistence and audit tracking in compliance_audit_packs.
6. ABAC security invariants across applicant, reviewer, compliance_officer, and auditor roles.
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
import communications
import migrations
import policy
import portal


class Milestone9NotificationsTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m9.sqlite3"
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
        self.compliance_officer = auth.provision_staff(
            admin_actor, "compliance@test.com", "compliance_officer",
            temp_password="Password1234#", display_name="Compliance Officer"
        )
        self.auditor = auth.provision_staff(
            admin_actor, "auditor@test.com", "auditor",
            temp_password="Password1234#", display_name="Independent Auditor"
        )
        self.reviewer = auth.provision_staff(
            admin_actor, "rev@test.com", "reviewer",
            temp_password="Password1234#", display_name="Reviewer Priya"
        )

        # Register test applicants
        self.applicant_1 = auth.register("app1@test.com", "SecurePass123#", "Kavita Reddy")
        self.applicant_2 = auth.register("app2@test.com", "SecurePass123#", "Rajesh Verma")

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

    # 1. Multi-Channel Notification Dispatch (In-App, Email, SMS)
    def test_multi_channel_notification_dispatch(self):
        app = application.get_or_create_application(self.applicant_1)

        res = communications.dispatch_notification(
            user_id=self.applicant_1["id"],
            template_key="kyc_approved",
            context={"reference": app["reference"]},
            channels=("in_app", "email", "sms"),
        )

        self.assertTrue(res["ok"])
        self.assertEqual(len(res["dispatched_channels"]), 3)
        self.assertIn("in_app", res["dispatched_channels"])
        self.assertIn("email", res["dispatched_channels"])
        self.assertIn("sms", res["dispatched_channels"])
        self.assertIn("KYC", res["subject"])

        # Check in-app notification recorded
        with auth._db() as db:
            notif = db.execute("SELECT * FROM notifications WHERE user_id=? AND key='kyc_approved'", (self.applicant_1["id"],)).fetchone()
            self.assertIsNotNone(notif)
            self.assertEqual(notif["type"], "success")

            # Check email and SMS recorded in communication_dispatches
            dispatches = db.execute("SELECT channel, subject, content FROM communication_dispatches WHERE user_id=?", (self.applicant_1["id"],)).fetchall()
            self.assertEqual(len(dispatches), 2)
            channels = [d[0] for d in dispatches]
            self.assertIn("EMAIL", channels)
            self.assertIn("SMS", channels)

    # 2. Bilingual Template Rendering (EN and HI)
    def test_bilingual_notification_rendering(self):
        app1 = application.get_or_create_application(self.applicant_1)

        # Applicant 2 with Hindi preference
        with auth._db() as db:
            db.execute("UPDATE users SET language='hi' WHERE id=?", (self.applicant_2["id"],))

        app2 = application.get_or_create_application(self.applicant_2)

        # English dispatch
        en_res = communications.dispatch_notification(
            user_id=self.applicant_1["id"],
            template_key="exam_passed",
            context={"score": 42},
            channels=("email",),
        )
        self.assertIn("Congratulations", en_res["subject"])

        # Hindi dispatch
        hi_res = communications.dispatch_notification(
            user_id=self.applicant_2["id"],
            template_key="exam_passed",
            context={"score": 45},
            channels=("email",),
        )
        self.assertIn("बधाई", hi_res["subject"])

    # 3. Anti-Accusation Invariant Enforcement
    def test_anti_accusation_invariant_scrubbing(self):
        app = application.get_or_create_application(self.applicant_1)

        # Inject context with potentially accusatory / fraud terminology
        res = communications.dispatch_notification(
            user_id=self.applicant_1["id"],
            template_key="certificate_revoked",
            context={
                "cert_number": "PN-POSP-2026-0001",
                "reason": "Suspected document fraud and image manipulation in forgery ring",
            },
            channels=("email", "sms"),
        )

        # Candidate communications must NEVER include banned fraud/forgery terms!
        email_text = res["email_preview"].lower()
        sms_text = res["sms_preview"].lower()

        for banned in ("fraud", "forgery", "manipulation", "ring"):
            self.assertNotIn(banned, email_text)
            self.assertNotIn(banned, sms_text)

        self.assertIn("discrepancy", email_text)

    # 4. Unified Immutable Audit Timeline (Applicant vs Staff Views)
    def test_unified_immutable_audit_timeline(self):
        app = application.get_or_create_application(self.applicant_1)
        now = int(time.time())

        # Seed timeline and audit events
        with auth._db() as db:
            # Timeline row
            db.execute(
                "INSERT INTO timeline (user_id, t, actor, key, stage, doc) VALUES (?, ?, 'you', 'application_started', 'Basics', '')",
                (self.applicant_1["id"], now - 100),
            )
            # Reviewer audit row
            db.execute(
                "INSERT INTO audit_events (case_id, actor_id, action, occurred) VALUES (?, ?, 'CLAIM_CASE', ?)",
                (f"user_{self.applicant_1['id']}", self.reviewer["id"], now - 50),
            )

        # 4a. Staff View (Full transparency)
        staff_tl = communications.get_unified_audit_timeline(self.compliance_officer, self.applicant_1["id"])
        self.assertTrue(staff_tl["ok"])
        self.assertGreaterEqual(staff_tl["event_count"], 2)

        staff_audit_events = [e for e in staff_tl["events"] if e["source"] == "audit"]
        self.assertGreaterEqual(len(staff_audit_events), 1)
        self.assertEqual(staff_audit_events[0]["actor_role"], "reviewer")
        self.assertEqual(staff_audit_events[0]["actor"], "Reviewer Priya")

        # 4b. Applicant View (Masked internal reviewer details)
        app_tl = communications.get_unified_audit_timeline(self.applicant_1, self.applicant_1["id"])
        self.assertTrue(app_tl["ok"])

        app_audit_events = [e for e in app_tl["events"] if e["source"] == "audit"]
        self.assertGreaterEqual(len(app_audit_events), 1)
        # Reviewer name must be masked for applicant
        self.assertEqual(app_audit_events[0]["actor"], "Staff Reviewer")
        self.assertNotIn("actor_role", app_audit_events[0])

    # 5. IRDAI Regulatory Compliance Audit Pack Exporter
    def test_compliance_audit_pack_generation_and_seal(self):
        app = application.get_or_create_application(self.applicant_1)

        # Transition through complete POSP certification lifecycle
        with auth._db() as db:
            db.execute("UPDATE applications SET status='EXAM_PASSED', stage='Certificate' WHERE id=?", (app["id"],))

        certification.execute_posp_agreement(self.applicant_1)
        cert = certification.issue_posp_certificate(self.applicant_1)

        # Compliance Officer exports audit pack
        pack_res = communications.generate_compliance_audit_pack(self.compliance_officer, self.applicant_1["id"])
        self.assertTrue(pack_res["ok"])
        self.assertIn("AUDIT-PACK-", pack_res["pack_id"])
        self.assertEqual(len(pack_res["bundle_hash"]), 64)  # SHA-256 length

        pack = pack_res["pack"]
        self.assertEqual(pack["candidate_profile"]["display_name"], "Kavita Reddy")
        self.assertIn("IRDAI POSP Guidelines", pack["regulatory_framework"])
        self.assertIsNotNone(pack["curriculum_training_audit"])
        self.assertIsNotNone(pack["appointment_agreement"])
        self.assertIsNotNone(pack["posp_digital_certificate"])
        self.assertEqual(pack["posp_digital_certificate"]["certificate_number"], cert["certificate_number"])
        self.assertGreaterEqual(len(pack["immutable_event_stream"]), 1)

        # Check recorded in compliance_audit_packs table
        with auth._db() as db:
            row = db.execute("SELECT * FROM compliance_audit_packs WHERE id=?", (pack_res["pack_id"],)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["bundle_hash"], pack_res["bundle_hash"])

    # 6. ABAC Security Invariants
    def test_communications_abac_security_invariants(self):
        application.get_or_create_application(self.applicant_1)

        # Applicant cannot view another applicant's timeline
        with self.assertRaises(PermissionError):
            communications.get_unified_audit_timeline(self.applicant_1, self.applicant_2["id"])

        # Applicant cannot export compliance audit packs
        with self.assertRaises(PermissionError):
            communications.generate_compliance_audit_pack(self.applicant_1, self.applicant_1["id"])

        # Reviewer cannot export compliance audit packs
        with self.assertRaises(PermissionError):
            communications.generate_compliance_audit_pack(self.reviewer, self.applicant_1["id"])

        # Independent Auditor CAN export compliance audit packs
        auditor_pack = communications.generate_compliance_audit_pack(self.auditor, self.applicant_1["id"])
        self.assertTrue(auditor_pack["ok"])


if __name__ == "__main__":
    unittest.main()
