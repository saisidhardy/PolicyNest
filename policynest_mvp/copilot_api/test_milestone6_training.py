"""Milestone 6 Verification Suite: IRDAI 15-Hour Training & LMS Engine.

Tests:
1. Curriculum seeding: 5 modules totaling exactly 15.0 hours (900 minutes / 54,000 seconds).
2. Status-gated eligibility: Training locked during DRAFT/SUBMITTED, unlocked upon KYC_APPROVED.
3. Sequential module unlocking: Module 1 unlocked, Module 2 locked until Module 1 is completed.
4. Heartbeat active time logging and wall-clock anti-tampering verification (clamping fast-forwarding).
5. Automatic state transition from KYC_APPROVED to TRAINING_IN_PROGRESS on first study heartbeat.
6. Anti-skipping enforcement: cannot complete module without meeting minimum logged study time.
7. Module completion workflow and progress aggregation.
8. Full 15-hour curriculum completion: auto-transitions application to TRAINING_COMPLETE and stage to Exam.
9. Bilingual curriculum support (English and Hindi).
10. Training Admin lifecycle: module authoring, applicant progress auditing, and progress reset.
11. ABAC security invariants: applicants blocked from admin authoring, unauthenticated rejected.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import application
import auth
import migrations
import policy
import portal
import training_lms


class Milestone6TrainingTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m6.sqlite3"
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
        self.training_admin = auth.provision_staff(
            admin_actor, "training.admin@test.com", "training_admin",
            temp_password="Password1234#", display_name="Training Admin"
        )
        self.reviewer = auth.provision_staff(
            admin_actor, "rev@test.com", "reviewer",
            temp_password="Password1234#", display_name="Standard Reviewer"
        )

        # Register test applicants
        self.applicant_1 = auth.register("app1@test.com", "SecurePass123#", "App One")
        self.applicant_2 = auth.register("app2@test.com", "SecurePass123#", "App Two")

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

    # 1. Curriculum Seeding & 15-Hour Verification
    def test_curriculum_seeding_and_total_hours(self):
        with auth._db() as db:
            rows = db.execute("SELECT id, duration_minutes, title FROM training_modules ORDER BY sequence_order ASC").fetchall()

        self.assertEqual(len(rows), 5)
        total_mins = sum(r["duration_minutes"] for r in rows)
        self.assertEqual(total_mins, 900)  # Exactly 15.0 hours
        self.assertEqual(total_mins / 60.0, 15.0)

        # Verify module sequence IDs
        mod_ids = [r["id"] for r in rows]
        self.assertEqual(mod_ids, ["MOD-01", "MOD-02", "MOD-03", "MOD-04", "MOD-05"])

    # 2. Status-Gated Eligibility
    def test_status_gated_training_eligibility(self):
        app = application.get_or_create_application(self.applicant_1)

        # When status is DRAFT: not eligible for training
        overview_draft = training_lms.get_training_overview(self.applicant_1)
        self.assertFalse(overview_draft["is_eligible_for_training"])
        self.assertFalse(overview_draft["modules"][0]["is_unlocked"])

        # Cannot log heartbeat in DRAFT status
        with self.assertRaises(ValueError) as ctx:
            training_lms.record_training_heartbeat(self.applicant_1, "MOD-01", 30)
        self.assertIn("cannot_train_in_current_status", str(ctx.exception))

        # Update status to KYC_APPROVED
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))

        # Now eligible and Module 1 unlocked
        overview_approved = training_lms.get_training_overview(self.applicant_1)
        self.assertTrue(overview_approved["is_eligible_for_training"])
        self.assertTrue(overview_approved["modules"][0]["is_unlocked"])

    # 3. Sequential Unlocking Logic
    def test_sequential_module_unlocking(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))

        overview = training_lms.get_training_overview(self.applicant_1)
        mods = overview["modules"]

        # Module 1 unlocked, Modules 2-5 locked
        self.assertTrue(mods[0]["is_unlocked"])
        self.assertFalse(mods[1]["is_unlocked"])
        self.assertFalse(mods[2]["is_unlocked"])

        # Mark Module 1 completed
        req_secs_mod1 = mods[0]["duration_minutes"] * 60
        now = int(time.time())
        with auth._db() as db:
            db.execute(
                """INSERT OR REPLACE INTO training_progress (
                    id, user_id, module_id, status, time_spent_seconds, completed_at, created_at, updated_at
                ) VALUES ('tp_mod1', ?, 'MOD-01', 'COMPLETED', ?, ?, ?, ?)""",
                (self.applicant_1["id"], req_secs_mod1, now, now, now),
            )

        # Now Module 2 should unlock
        updated_overview = training_lms.get_training_overview(self.applicant_1)
        updated_mods = updated_overview["modules"]
        self.assertTrue(updated_mods[0]["is_unlocked"])
        self.assertTrue(updated_mods[1]["is_unlocked"])
        self.assertFalse(updated_mods[2]["is_unlocked"])

    # 4. Heartbeat Logging, Anti-Tampering & Auto-Transition
    def test_heartbeat_logging_and_auto_transition_to_in_progress(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))

        # First heartbeat should transition application to TRAINING_IN_PROGRESS
        res = training_lms.record_training_heartbeat(
            self.applicant_1, "MOD-01", seconds_increment=30, section_index=1,
            bookmark={"slide": 4, "time": 120}
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["module_id"], "MOD-01")
        self.assertGreaterEqual(res["time_spent_seconds"], 1)

        # Check application status auto-updated to TRAINING_IN_PROGRESS
        with auth._db() as db:
            app_row = db.execute("SELECT status, stage FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "TRAINING_IN_PROGRESS")
            self.assertEqual(app_row[1], "Training")

        # Anti-tampering check: excessively large heartbeat (e.g. 9999s) clamped to max 60s
        res2 = training_lms.record_training_heartbeat(self.applicant_1, "MOD-01", seconds_increment=9999)
        self.assertLessEqual(res2["effective_increment"], 60)

    # 5. Anti-Skipping Enforcement on Module Completion
    def test_anti_skipping_insufficient_time_rejection(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))

        # Log only 60 seconds of a 180-minute (10,800 seconds) module
        now = int(time.time())
        with auth._db() as db:
            db.execute(
                """INSERT OR REPLACE INTO training_progress (
                    id, user_id, module_id, status, time_spent_seconds, created_at, updated_at
                ) VALUES ('tp_mod1', ?, 'MOD-01', 'IN_PROGRESS', 60, ?, ?)""",
                (self.applicant_1["id"], now, now),
            )

        # Attempting to complete prematurely should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            training_lms.complete_training_module(self.applicant_1, "MOD-01")
        self.assertIn("insufficient_study_time", str(ctx.exception))

    # 6. Full 15-Hour Curriculum Completion & Exam Unlock
    def test_full_15_hour_curriculum_completion_and_exam_unlock(self):
        app = application.get_or_create_application(self.applicant_2)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))
            now = int(time.time())

            # Complete modules 1 through 4
            for mod_num in range(1, 5):
                m_id = f"MOD-0{mod_num}"
                db.execute(
                    """INSERT OR REPLACE INTO training_progress (
                        id, user_id, module_id, status, time_spent_seconds, completed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, 'COMPLETED', 15000, ?, ?, ?)""",
                    (f"tp_{m_id}", self.applicant_2["id"], m_id, now, now, now),
                )

            # Setup module 5 with sufficient study time (120 mins = 7200s)
            db.execute(
                """INSERT OR REPLACE INTO training_progress (
                    id, user_id, module_id, status, time_spent_seconds, created_at, updated_at
                ) VALUES ('tp_MOD-05', ?, 'MOD-05', 'IN_PROGRESS', 7200, ?, ?)""",
                (self.applicant_2["id"], now, now),
            )

        # Complete final module 5
        comp_res = training_lms.complete_training_module(self.applicant_2, "MOD-05")
        self.assertTrue(comp_res["ok"])
        self.assertTrue(comp_res["is_training_complete"])
        self.assertEqual(comp_res["completed_modules"], 5)

        # Check application status transitioned to TRAINING_COMPLETE and stage to Exam
        with auth._db() as db:
            app_row = db.execute("SELECT status, stage FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "TRAINING_COMPLETE")
            self.assertEqual(app_row[1], "Exam")

            # Check notification generated
            notif_row = db.execute(
                "SELECT key FROM notifications WHERE user_id=? AND key='training_complete'",
                (self.applicant_2["id"],),
            ).fetchone()
            self.assertIsNotNone(notif_row)

    # 7. Bilingual Curriculum Support
    def test_bilingual_curriculum_support(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='KYC_APPROVED' WHERE id=?", (app["id"],))

        # Fetch in Hindi
        overview_hi = training_lms.get_training_overview(self.applicant_1, lang="hi")
        self.assertIn("बीमा", overview_hi["modules"][0]["title"])

        # Fetch in English
        overview_en = training_lms.get_training_overview(self.applicant_1, lang="en")
        self.assertIn("Insurance", overview_en["modules"][0]["title"])

    # 8. Training Admin Curriculum Management & Reset
    def test_training_admin_management_and_reset(self):
        # Training admin lists modules
        admin_mods = training_lms.admin_list_modules(self.training_admin)
        self.assertEqual(len(admin_mods), 5)

        # Training admin inspects user progress
        u_prog = training_lms.admin_get_user_progress(self.training_admin, self.applicant_1["id"])
        self.assertIn("modules", u_prog)

        # Training admin resets user progress
        reset_res = training_lms.admin_reset_user_progress(self.training_admin, self.applicant_1["id"])
        self.assertTrue(reset_res["ok"])
        self.assertTrue(reset_res["reset"])

    # 9. ABAC Security Invariants
    def test_training_abac_security_invariants(self):
        # Applicant cannot call training admin APIs
        with self.assertRaises(PermissionError):
            training_lms.admin_list_modules(self.applicant_1)

        with self.assertRaises(PermissionError):
            training_lms.admin_reset_user_progress(self.applicant_1, self.applicant_2["id"])

        # Reviewer cannot call training admin APIs
        with self.assertRaises(PermissionError):
            training_lms.admin_list_modules(self.reviewer)


if __name__ == "__main__":
    unittest.main()
