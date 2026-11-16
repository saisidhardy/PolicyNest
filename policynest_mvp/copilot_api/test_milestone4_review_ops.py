"""Unit and Integration Tests for Milestone 4: Review Operations & Staff Cockpit.

Tests:
1. Multi-Queue Review Operations (my_queue, unassigned, escalated, rework, fraud).
2. Atomic Case Claiming, Concurrency Locking, and Release.
3. Workload Rebalancing and Role-Based Case Reassignment.
4. Comprehensive Case Dossier Aggregation for Staff Cockpit.
5. Structured Decision Engine:
   - APPROVE -> KYC_APPROVED
   - REQUEST_CHANGES -> NEEDS_MORE_INFO with slot defect updates
   - REJECT -> REJECTED with regulatory rule citation and cooling-off period
   - ESCALATE -> ESCALATED for Senior Reviewer
   - FLAG_FRAUD -> FRAUD_HOLD with risk_hold and fraud_cases ticket
6. Appeals Lifecycle & Dispute Resolution:
   - Applicant appeal filing with anti-leak protection (no raw Aadhaar/PAN)
   - Reviewer bias prevention: standard reviewer cannot resolve appeals
   - Senior Reviewer / Compliance Officer resolution (OVERTURNED / UPHELD)
7. Audit Trail Immutability.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

import auth
import migrations
import policy
import portal
import review_ops


class Milestone4ReviewOpsTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m4.sqlite3"
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
        self.reviewer_1 = auth.provision_staff(admin_actor, "rev1@policynest.com", "reviewer", temp_password="Password1234#", display_name="Reviewer One")
        self.reviewer_2 = auth.provision_staff(admin_actor, "rev2@policynest.com", "reviewer", temp_password="Password1234#", display_name="Reviewer Two")
        self.senior_reviewer = auth.provision_staff(admin_actor, "sr_rev@policynest.com", "senior_reviewer", temp_password="Password1234#", display_name="Senior Reviewer")
        self.operations = auth.provision_staff(admin_actor, "ops@policynest.com", "operations", temp_password="Password1234#", display_name="Operations Lead")
        self.compliance = auth.provision_staff(admin_actor, "comp@policynest.com", "compliance_officer", temp_password="Password1234#", display_name="Compliance Officer")

        # Register test applicants
        self.applicant_1 = auth.register("app1@example.com", "SecurePass123#", "Saisidhardh Vajja")
        self.applicant_2 = auth.register("app2@example.com", "SecurePass123#", "Priya Sharma")

        # Create applications & cases
        with auth._db() as db:
            now = int(time.time())
            # Case 1: unassigned, submitted
            db.execute(
                """INSERT OR REPLACE INTO applications (id, user_id, reference, status, stage, submitted_at, created_at, updated_at, details)
                   VALUES (1, ?, 'PN-2026-00001', 'SUBMITTED', 'Documents', ?, ?, ?, '{"name":"Saisidhardh Vajja"}')""",
                (self.applicant_1["id"], now, now, now),
            )
            db.execute(
                """INSERT OR REPLACE INTO cases (id, applicant_id, reviewer_id, status, created_at, updated_at)
                   VALUES ('PN-2026-00001', ?, NULL, 'SUBMITTED', ?, ?)""",
                (self.applicant_1["id"], now, now),
            )

            # Case 2: assigned to reviewer_1
            db.execute(
                """INSERT OR REPLACE INTO applications (id, user_id, reference, status, stage, submitted_at, created_at, updated_at, details)
                   VALUES (2, ?, 'PN-2026-00002', 'IN_REVIEW', 'Documents', ?, ?, ?, '{"name":"Priya Sharma"}')""",
                (self.applicant_2["id"], now, now, now),
            )
            db.execute(
                """INSERT OR REPLACE INTO cases (id, applicant_id, reviewer_id, status, created_at, updated_at)
                   VALUES ('PN-2026-00002', ?, ?, 'IN_REVIEW', ?, ?)""",
                (self.applicant_2["id"], self.reviewer_1["id"], now, now),
            )

    def tearDown(self):
        if self.orig_db_env:
            os.environ["POLICYNEST_DB_PATH"] = self.orig_db_env
        else:
            os.environ.pop("POLICYNEST_DB_PATH", None)
        if self.orig_jwt_env:
            os.environ["JWT_SECRET"] = self.orig_jwt_env
        else:
            os.environ.pop("JWT_SECRET", None)
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Multi-Queue Review Operations
    # -------------------------------------------------------------
    def test_multi_queue_retrieval_and_filtering(self):
        # Reviewer 1 views their queue -> should see Case 2
        q_rev1 = review_ops.get_queues(self.reviewer_1, queue_type="my_queue")
        self.assertTrue(q_rev1["ok"])
        self.assertEqual(q_rev1["total"], 1)
        self.assertEqual(q_rev1["cases"][0]["case_id"], "PN-2026-00002")

        # Operations views unassigned queue -> should see Case 1
        q_unassigned = review_ops.get_queues(self.operations, queue_type="unassigned")
        self.assertTrue(q_unassigned["ok"])
        self.assertEqual(q_unassigned["total"], 1)
        self.assertEqual(q_unassigned["cases"][0]["case_id"], "PN-2026-00001")

        # Summary bucket counts
        counts = q_unassigned["counts"]
        self.assertEqual(counts["unassigned"], 1)
        self.assertEqual(counts["all"], 2)

        # Applicant attempting to access review queue is blocked with 403
        with self.assertRaises(PermissionError):
            review_ops.get_queues(self.applicant_1, queue_type="my_queue")

    # -------------------------------------------------------------
    # 2. Atomic Case Claiming & Concurrency Locking
    # -------------------------------------------------------------
    def test_atomic_case_claiming_and_locking(self):
        # Reviewer 1 claims unassigned Case 1
        claim_res = review_ops.claim_case(self.reviewer_1, "PN-2026-00001")
        self.assertTrue(claim_res["ok"])
        self.assertEqual(claim_res["reviewer_id"], self.reviewer_1["id"])

        # Reviewer 2 attempts to claim the same case concurrently -> blocked with 409
        with self.assertRaises(ValueError) as ctx:
            review_ops.claim_case(self.reviewer_2, "PN-2026-00001")
        self.assertEqual(str(ctx.exception), "case_already_claimed")

    # -------------------------------------------------------------
    # 3. Case Release & Workload Reassignment
    # -------------------------------------------------------------
    def test_case_release_and_workload_reassignment(self):
        # Reviewer 1 releases Case 2
        rel_res = review_ops.release_case(self.reviewer_1, "PN-2026-00002")
        self.assertTrue(rel_res["ok"])
        self.assertTrue(rel_res["released"])

        # Case 2 should now be in unassigned queue
        q_unassigned = review_ops.get_queues(self.operations, queue_type="unassigned")
        self.assertEqual(q_unassigned["counts"]["unassigned"], 2)

        # Operations reassigns Case 2 to Reviewer 2
        reassign_res = review_ops.reassign_case(self.operations, "PN-2026-00002", self.reviewer_2["id"])
        self.assertTrue(reassign_res["ok"])
        self.assertEqual(reassign_res["new_reviewer_id"], self.reviewer_2["id"])

        # Normal reviewer cannot reassign cases across staff (privilege escalation prevention)
        with self.assertRaises(PermissionError):
            review_ops.reassign_case(self.reviewer_1, "PN-2026-00002", self.reviewer_1["id"])

    # -------------------------------------------------------------
    # 4. Comprehensive Case Dossier Aggregation
    # -------------------------------------------------------------
    def test_comprehensive_case_dossier_aggregation(self):
        dossier = review_ops.get_case_dossier(self.reviewer_1, "PN-2026-00002")
        self.assertEqual(dossier["case"]["id"], "PN-2026-00002")
        self.assertEqual(dossier["applicant"]["display_name"], "Priya Sharma")
        self.assertEqual(dossier["application"]["status"], "IN_REVIEW")
        self.assertIn("documents", dossier)
        self.assertIn("verifications", dossier)
        self.assertIn("cross_checks", dossier)
        self.assertIn("notes", dossier)
        self.assertIn("audit_events", dossier)

        # Applicant 1 cannot access Applicant 2's dossier
        with self.assertRaises(PermissionError):
            review_ops.get_case_dossier(self.applicant_1, "PN-2026-00002")

    # -------------------------------------------------------------
    # 5. Structured Decision Engine Tests
    # -------------------------------------------------------------
    def test_reviewer_decide_approve(self):
        res = review_ops.decide_case(
            actor=self.reviewer_1,
            case_id="PN-2026-00002",
            status="KYC_APPROVED",
            note="All uploaded documents and cross-checks verified successfully.",
            rule="§4.1",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "KYC_APPROVED")

        # Verify application status also updated
        with auth._db() as db:
            app_status = db.execute("SELECT status FROM applications WHERE user_id=?", (self.applicant_2["id"],)).fetchone()[0]
            self.assertEqual(app_status, "KYC_APPROVED")

    def test_reviewer_decide_request_changes_and_slot_defects(self):
        # Insert a document record for Case 2
        with auth._db() as db:
            db.execute(
                """INSERT OR REPLACE INTO document_records (
                    id, application_id, user_id, slot, doc_type, mime_type,
                    file_size, storage_path, sha256_hash, status, created_at, updated_at
                ) VALUES ('doc_pan_01', 2, ?, 'PAN', 'pan', 'image/jpeg', 50000, '/tmp/pan', 'hash123', 'UPLOADED', 100, 100)""",
                (self.applicant_2["id"],),
            )

        res = review_ops.decide_case(
            actor=self.reviewer_1,
            case_id="PN-2026-00002",
            status="NEEDS_MORE_INFO",
            note="PAN card has excessive glare across the PAN number.",
            rule="§4.1",
            slot_defects={"PAN": "Flash glare obscuring PAN number"},
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "NEEDS_MORE_INFO")

        # Verify document_records updated for defective slot
        with auth._db() as db:
            doc_row = db.execute("SELECT status, rejection_reason FROM document_records WHERE id='doc_pan_01'").fetchone()
            self.assertEqual(doc_row[0], "REUPLOAD_NEEDED")
            self.assertEqual(doc_row[1], "Flash glare obscuring PAN number")

    def test_reviewer_decide_reject_and_cooling_off(self):
        res = review_ops.decide_case(
            actor=self.reviewer_1,
            case_id="PN-2026-00002",
            status="REJECTED",
            note="Secondary education certificate could not be authenticated.",
            rule="§4.2",
            cooling_off_days=30,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "REJECTED")
        self.assertIsNotNone(res["cooling_off_until"])

        with auth._db() as db:
            case_row = db.execute("SELECT status, cooling_off_until FROM cases WHERE id='PN-2026-00002'").fetchone()
            self.assertEqual(case_row[0], "REJECTED")
            self.assertGreater(case_row[1], int(time.time()))

    def test_reviewer_decide_escalate(self):
        res = review_ops.decide_case(
            actor=self.reviewer_1,
            case_id="PN-2026-00002",
            status="ESCALATED",
            note="Name transliteration discrepancy requires Senior Reviewer discretion.",
            rule="§4.1",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "ESCALATED")

        # Appears in escalated queue
        q_esc = review_ops.get_queues(self.senior_reviewer, queue_type="escalated")
        self.assertEqual(q_esc["total"], 1)

    def test_reviewer_decide_flag_fraud_and_risk_hold(self):
        res = review_ops.decide_case(
            actor=self.reviewer_1,
            case_id="PN-2026-00002",
            status="FRAUD_HOLD",
            note="Tampered marksheet metadata detected during forensic inspection.",
            rule="§4.4",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "FRAUD_HOLD")

        # Check risk_hold placed on application and fraud case created
        with auth._db() as db:
            app_row = db.execute("SELECT status, risk_hold FROM applications WHERE user_id=?", (self.applicant_2["id"],)).fetchone()
            self.assertEqual(app_row[0], "FRAUD_HOLD")
            self.assertEqual(app_row[1], 1)

            fraud_row = db.execute("SELECT status, anomaly_type FROM fraud_cases WHERE applicant_id=?", (self.applicant_2["id"],)).fetchone()
            self.assertIsNotNone(fraud_row)
            self.assertEqual(fraud_row[0], "FLAGGED")

    # -------------------------------------------------------------
    # 6. Formal Appeals Lifecycle & Anti-Leak Rules
    # -------------------------------------------------------------
    def test_formal_appeal_submission_and_anti_leak(self):
        # Set Case 1 to REJECTED first
        with auth._db() as db:
            db.execute("UPDATE cases SET status='REJECTED' WHERE id='PN-2026-00001'")
            db.execute("UPDATE applications SET status='REJECTED' WHERE user_id=?", (self.applicant_1["id"],))

        # Applicant 1 files appeal
        appeal_res = review_ops.submit_appeal(
            applicant_user=self.applicant_1,
            case_id="PN-2026-00001",
            explanation="The name spelling difference is due to my marriage certificate declaration.",
        )
        self.assertTrue(appeal_res["ok"])
        self.assertEqual(appeal_res["status"], "OPEN")
        appeal_ref = appeal_res["appeal_reference"]
        self.assertTrue(appeal_ref.startswith("AP-"))

        # Anti-leak check: Attempting to submit raw Aadhaar number in explanation is rejected
        with self.assertRaises(ValueError) as ctx:
            review_ops.submit_appeal(
                applicant_user=self.applicant_1,
                case_id="PN-2026-00001",
                explanation="Here is my Aadhaar 9999 4105 1234 to prove my identity.",
            )
        self.assertEqual(str(ctx.exception), "do_not_include_identity_numbers")

        # Applicant 2 cannot appeal Applicant 1's case
        with self.assertRaises(PermissionError):
            review_ops.submit_appeal(
                applicant_user=self.applicant_2,
                case_id="PN-2026-00001",
                explanation="Attempting unauthorized appeal on another case.",
            )

    def test_appeals_decision_by_senior_reviewer_and_compliance(self):
        # Set up appeal
        with auth._db() as db:
            now = int(time.time())
            db.execute("UPDATE cases SET status='REJECTED' WHERE id='PN-2026-00001'")
            db.execute(
                """INSERT INTO appeals (id, case_id, explanation, status, created, evidence)
                   VALUES ('AP-TEST001', 'PN-2026-00001', 'Valid marriage declaration provided.', 'OPEN', ?, '{}')""",
                (now,),
            )

        # Senior reviewer lists appeals
        appeals_list = review_ops.list_appeals(self.senior_reviewer)
        self.assertTrue(len(appeals_list) >= 1)

        # Reviewer 1 (standard reviewer) attempts to resolve appeal -> FORBIDDEN (anti-bias invariant)
        with self.assertRaises(PermissionError) as ctx:
            review_ops.decide_appeal(
                actor=self.reviewer_1,
                appeal_reference="AP-TEST001",
                verdict="OVERTURNED",
                response_text="Standard reviewer trying to resolve appeal.",
            )
        self.assertIn("forbidden_only_senior_authority_can_resolve_appeals", str(ctx.exception))

        # Senior Reviewer resolves and overturns appeal
        overturn_res = review_ops.decide_appeal(
            actor=self.senior_reviewer,
            appeal_reference="AP-TEST001",
            verdict="OVERTURNED",
            response_text="The marriage declaration resolves the name discrepancy.",
            restore_status="KYC_APPROVED",
        )
        self.assertTrue(overturn_res["ok"])
        self.assertEqual(overturn_res["verdict"], "OVERTURNED")
        self.assertEqual(overturn_res["case_status"], "KYC_APPROVED")

        # Verify case & application restored to KYC_APPROVED
        with auth._db() as db:
            case_status = db.execute("SELECT status FROM cases WHERE id='PN-2026-00001'").fetchone()[0]
            app_status = db.execute("SELECT status FROM applications WHERE user_id=?", (self.applicant_1["id"],)).fetchone()[0]
            self.assertEqual(case_status, "KYC_APPROVED")
            self.assertEqual(app_status, "KYC_APPROVED")

    # -------------------------------------------------------------
    # 7. Audit Trail Immutability
    # -------------------------------------------------------------
    def test_audit_trail_immutability(self):
        with auth._db() as db:
            # Audit events cannot be tampered with via UPDATE or DELETE triggers
            audit_id = db.execute("SELECT id FROM audit_events LIMIT 1").fetchone()
            if not audit_id:
                now = int(time.time())
                db.execute("INSERT INTO audit_events (case_id, actor_id, action, occurred) VALUES ('PN-TEST', 1, 'TEST', ?)", (now,))
                audit_id = db.execute("SELECT last_insert_rowid()").fetchone()

            target_id = audit_id[0]

            with self.assertRaises(Exception):
                db.execute("UPDATE audit_events SET action='TAMPERED' WHERE id=?", (target_id,))

            with self.assertRaises(Exception):
                db.execute("DELETE FROM audit_events WHERE id=?", (target_id,))


if __name__ == "__main__":
    unittest.main()
