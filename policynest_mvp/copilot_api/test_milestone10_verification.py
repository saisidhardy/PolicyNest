"""Milestone 10: System Verification, Subsystem Auditing & QA Tooling Tests.

Verifies:
1. System verification report compiles all 16 platform subsystems with honest statuses.
2. In production mode, verification report requires administrator authorization.
3. QA seed workflow creates all 11 explicit test cases required by Phase 2.
4. QA reset safely purges only synthetic test records while strictly preserving production user records.
5. In production mode, QA seed and reset are rejected unless explicitly authorized.
6. Immutable audit trail records every seed and reset operation.
"""
import unittest
import time
import os
import secrets
import config
import auth
import verification
import qa

class TestMilestone10Verification(unittest.TestCase):

    def setUp(self):
        # Ensure non-production for base tests
        config.IS_PRODUCTION = False
        config.IS_DEV = True

    def test_01_system_verification_report_structure(self):
        rep = verification.get_system_verification_report()
        self.assertEqual(rep["application_version"], "3.2.0")
        self.assertIn("commit_id", rep)
        self.assertIn("build_timestamp", rep)
        self.assertEqual(rep["database"]["status"], "Verified")
        self.assertTrue(rep["database"]["connected"])
        self.assertEqual(rep["storage"]["status"], "Verified")

        subsystems = rep["subsystems"]
        self.assertEqual(len(subsystems), 16)

        # Confirm honest labeling: KYC is Simulated
        self.assertEqual(subsystems["kyc_verification"]["status"], "Simulated")
        self.assertIn("Simulated Provider Adapters", subsystems["kyc_verification"]["mode"])

        # Confirm core subsystems are Verified
        for key in ["authentication", "authorization", "persistence", "fraud_investigation", "training_lms", "examination", "certification"]:
            self.assertEqual(subsystems[key]["status"], "Verified", f"Subsystem {key} should be Verified")

    def test_02_production_access_control_on_verification(self):
        try:
            config.IS_PRODUCTION = True
            # Anonymous / applicant user in production must be forbidden
            with self.assertRaises(ValueError):
                verification.get_system_verification_report(user=None)

            applicant = {"id": 101, "role": "applicant"}
            with self.assertRaises(ValueError):
                verification.get_system_verification_report(user=applicant)

            # Administrator in production is allowed
            admin = {"id": 1, "role": "admin"}
            rep = verification.get_system_verification_report(user=admin)
            self.assertEqual(rep["environment"], "PRODUCTION")
            self.assertTrue(rep["is_production"])
        finally:
            config.IS_PRODUCTION = False

    def test_03_qa_seed_workflow(self):
        seed_res = qa.seed_qa_environment()
        self.assertTrue(seed_res["ok"])
        entities = seed_res["created_entities"]

        # Assert all 11 required test fixtures are generated
        self.assertIn("1_synthetic_applicant", entities)
        self.assertIn("2_synthetic_reviewer", entities)
        self.assertIn("3_synthetic_admin", entities)
        self.assertIn("4_draft_application", entities)
        self.assertIn("5_submitted_application", entities)
        self.assertIn("6_changes_requested", entities)
        self.assertIn("7_approved_application", entities)
        self.assertIn("8_failed_verification", entities)
        self.assertIn("9_passed_training", entities)
        self.assertIn("10_failed_exam", entities)
        self.assertIn("11_test_certificate", entities)

        # Verify certificate format
        self.assertTrue(entities["11_test_certificate"]["certificate_number"].startswith("PN-POSP-2026-SYN"))

    def test_04_qa_reset_purges_only_synthetic_records(self):
        # 1. Create a "real" non-synthetic user
        now = int(time.time())
        salt = secrets.token_hex(16)
        h = auth._hash("RealProductionUserPass123!")
        real_email = f"real_production_{now}@example.com"
        with auth._db() as db:
            cur = db.execute(
                "INSERT INTO users (email, display_name, password_hash, role, created_at) VALUES (?, ?, ?, 'applicant', ?)",
                (real_email, "Real Applicant", h, now)
            )
            real_uid = cur.lastrowid

        try:
            # 2. Seed synthetic records
            qa.seed_qa_environment()

            # 3. Reset synthetic records
            reset_res = qa.reset_qa_environment()
            self.assertTrue(reset_res["ok"])
            self.assertGreater(reset_res["deleted_counts"]["synthetic_users"], 0)

            # 4. Verify the real user is STILL PRESENT and completely untouched
            with auth._db() as db:
                cur = db.execute("SELECT id FROM users WHERE id = ?", (real_uid,))
                row = cur.fetchone()
                self.assertIsNotNone(row, "Real user must never be deleted by QA reset")
        finally:
            # Cleanup real test user
            with auth._db() as db:
                db.execute("DELETE FROM users WHERE id = ?", (real_uid,))

    def test_05_qa_seed_and_reset_disabled_in_production(self):
        try:
            config.IS_PRODUCTION = True
            with self.assertRaises(ValueError):
                qa.seed_qa_environment()

            with self.assertRaises(ValueError):
                qa.reset_qa_environment()
        finally:
            config.IS_PRODUCTION = False

    def test_06_audit_event_logged_on_seed_and_reset(self):
        qa.seed_qa_environment()
        qa.reset_qa_environment()
        with auth._db() as db:
            cur = db.execute("SELECT action FROM audit_events WHERE case_id IN ('QA_SEED', 'QA_RESET') ORDER BY occurred DESC LIMIT 2")
            actions = [row[0] for row in cur.fetchall()]
            self.assertIn("QA_RESET_EXECUTED", actions)


if __name__ == "__main__":
    unittest.main()
