"""Milestone 7 Verification Suite: IRDAI POSP Examination Engine.

Tests:
1. Question bank seeding: 50 authentic questions across 5 syllabus categories.
2. Status-gated eligibility: locked during DRAFT/TRAINING_IN_PROGRESS, unlocked on TRAINING_COMPLETE.
3. Exam session generation: randomized questions, 30-minute timer, NO correct answer keys leaked.
4. Proctoring incident tracking: tab-switch / window blur incident logging and flags.
5. In-flight session resumption: reconnecting within 30-minute window resumes existing attempt.
6. Server-side authoritative evaluation:
   - Passing attempt (>= 18/50): transitions to EXAM_PASSED and stage to Certificate.
   - Failing attempt (< 18/50): transitions to EXAM_FAILED and activates 24-hour retake cooldown.
7. Retake cooldown enforcement: re-attempt rejected before 24 hours elapse.
8. Exam Admin lifecycle: attempt inspection, incident review, and cooldown waiver override.
9. ABAC security invariants: applicants and standard reviewers blocked from exam administration.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import application
import auth
import examination
import migrations
import policy
import portal


class Milestone7ExamTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m7.sqlite3"
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
        self.exam_admin = auth.provision_staff(
            admin_actor, "exam.admin@test.com", "exam_admin",
            temp_password="Password1234#", display_name="Exam Admin"
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

    # 1. Question Bank Seeding
    def test_question_bank_seeding(self):
        with auth._db() as db:
            examination.seed_question_bank(db)
            count = db.execute("SELECT COUNT(*) FROM exam_question_bank").fetchone()[0]
            self.assertEqual(count, 50)

            # Check coverage across 5 categories (10 each)
            for cat in ("principles", "general", "life", "health", "ethics"):
                cat_count = db.execute("SELECT COUNT(*) FROM exam_question_bank WHERE category=?", (cat,)).fetchone()[0]
                self.assertEqual(cat_count, 10, f"Category {cat} should have 10 questions")

    # 2. Status-Gated Eligibility
    def test_status_gated_exam_eligibility(self):
        app = application.get_or_create_application(self.applicant_1)

        # In DRAFT: ineligible
        el_draft = examination.get_exam_eligibility(self.applicant_1)
        self.assertFalse(el_draft["eligible"])
        self.assertEqual(el_draft["reason"], "TRAINING_INCOMPLETE")

        # In TRAINING_IN_PROGRESS: ineligible
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_IN_PROGRESS' WHERE id=?", (app["id"],))

        el_training = examination.get_exam_eligibility(self.applicant_1)
        self.assertFalse(el_training["eligible"])

        # In TRAINING_COMPLETE: eligible
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        el_ready = examination.get_exam_eligibility(self.applicant_1)
        self.assertTrue(el_ready["eligible"])
        self.assertEqual(el_ready["reason"], "READY")
        self.assertEqual(el_ready["pass_mark_required"], 18)

    # 3. Exam Session Generation & Anti-Leak Check
    def test_exam_session_generation_no_key_leak(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session = examination.start_exam_session(self.applicant_1, lang="en")
        self.assertTrue(session["ok"])
        self.assertIn("exam_id", session)
        self.assertEqual(session["duration_seconds"], 1800)
        self.assertEqual(len(session["questions"]), 50)

        # Critical Security Test: Ensure NO correct_index or answer key is returned to client!
        for q in session["questions"]:
            self.assertNotIn("correct_index", q)
            self.assertNotIn("answer", q)
            self.assertIn("id", q)
            self.assertIn("question", q)
            self.assertIn("options", q)
            self.assertEqual(len(q["options"]), 4)

    # 4. Proctoring Incident Tracking
    def test_proctoring_incident_tracking(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session = examination.start_exam_session(self.applicant_1)
        exam_id = session["exam_id"]

        # Record tab switch
        inc1 = examination.record_exam_incident(self.applicant_1, exam_id, "TAB_SWITCH", "User focused other tab")
        self.assertTrue(inc1["ok"])
        self.assertEqual(inc1["incident_count"], 1)

        # Record multiple faces
        inc2 = examination.record_exam_incident(self.applicant_1, exam_id, "MULTIPLE_FACES", "Second face detected")
        self.assertEqual(inc2["incident_count"], 2)

        with auth._db() as db:
            attempt = db.execute("SELECT incident_flag, incident_notes FROM exam_attempts WHERE id=?", (exam_id,)).fetchone()
            self.assertEqual(attempt[0], 2)
            self.assertIn("TAB_SWITCH", attempt[1])
            self.assertIn("MULTIPLE_FACES", attempt[1])

    # 5. In-Flight Session Resumption
    def test_inflight_session_resumption(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session1 = examination.start_exam_session(self.applicant_1)
        self.assertFalse(session1["resumed"])

        # Second start call within 30 minutes returns same active session
        session2 = examination.start_exam_session(self.applicant_1)
        self.assertTrue(session2["resumed"])
        self.assertEqual(session2["exam_id"], session1["exam_id"])

    # 6. Authoritative Scoring: Passing Attempt (>= 18/50)
    def test_exam_passing_score_and_certificate_stage_transition(self):
        app = application.get_or_create_application(self.applicant_1)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session = examination.start_exam_session(self.applicant_1)
        exam_id = session["exam_id"]

        # Build passing answers: answer 30 correctly
        with auth._db() as db:
            q_rows = db.execute("SELECT id, correct_index FROM exam_question_bank").fetchall()
            key_map = {r[0]: r[1] for r in q_rows}

        answers = {}
        for idx, q in enumerate(session["questions"]):
            qid = q["id"]
            if idx < 30:
                answers[qid] = key_map[qid]  # Correct
            else:
                answers[qid] = (key_map[qid] + 1) % 4  # Incorrect

        res = examination.submit_exam_attempt(self.applicant_1, exam_id, answers)
        self.assertTrue(res["ok"])
        self.assertEqual(res["score"], 30)
        self.assertTrue(res["passed"])
        self.assertEqual(res["percentage"], 60.0)

        # Verify application transitioned to EXAM_PASSED and stage to Certificate
        with auth._db() as db:
            app_row = db.execute("SELECT status, stage FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "EXAM_PASSED")
            self.assertEqual(app_row[1], "Certificate")

            # Verify timeline and notification
            tl_row = db.execute("SELECT key FROM timeline WHERE user_id=? AND key='exam_passed'", (self.applicant_1["id"],)).fetchone()
            self.assertIsNotNone(tl_row)

    # 7. Authoritative Scoring: Failing Attempt (< 18/50) & 24h Cooldown
    def test_exam_failing_score_and_24h_cooldown(self):
        app = application.get_or_create_application(self.applicant_2)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session = examination.start_exam_session(self.applicant_2)
        exam_id = session["exam_id"]

        # Answer only 10 correctly (< 18)
        with auth._db() as db:
            q_rows = db.execute("SELECT id, correct_index FROM exam_question_bank").fetchall()
            key_map = {r[0]: r[1] for r in q_rows}

        answers = {}
        for idx, q in enumerate(session["questions"]):
            qid = q["id"]
            if idx < 10:
                answers[qid] = key_map[qid]  # Correct
            else:
                answers[qid] = (key_map[qid] + 1) % 4  # Incorrect

        res = examination.submit_exam_attempt(self.applicant_2, exam_id, answers)
        self.assertTrue(res["ok"])
        self.assertEqual(res["score"], 10)
        self.assertFalse(res["passed"])
        self.assertTrue(res["retake_cooldown_active"])
        self.assertIsNotNone(res["retake_available_at"])

        # Check application status set to EXAM_FAILED
        with auth._db() as db:
            app_row = db.execute("SELECT status FROM applications WHERE id=?", (app["id"],)).fetchone()
            self.assertEqual(app_row[0], "EXAM_FAILED")

        # Immediate retake attempt must be blocked by cooldown
        el_failed = examination.get_exam_eligibility(self.applicant_2)
        self.assertFalse(el_failed["eligible"])
        self.assertEqual(el_failed["reason"], "COOLDOWN_ACTIVE")
        self.assertGreater(el_failed["hours_remaining"], 23.0)

    # 8. Exam Admin Management & Cooldown Override
    def test_exam_admin_inspection_and_cooldown_override(self):
        # Setup applicant 2 with a failed attempt
        app = application.get_or_create_application(self.applicant_2)
        with auth._db() as db:
            db.execute("UPDATE applications SET status='TRAINING_COMPLETE' WHERE id=?", (app["id"],))

        session = examination.start_exam_session(self.applicant_2)
        exam_id = session["exam_id"]
        # Submit empty/failing answers
        examination.submit_exam_attempt(self.applicant_2, exam_id, {})

        # Admin lists attempts
        attempts = examination.admin_list_attempts(self.exam_admin)
        self.assertGreaterEqual(len(attempts), 1)

        # Admin overrides cooldown for applicant 2
        override_res = examination.admin_override_cooldown(self.exam_admin, self.applicant_2["id"])
        self.assertTrue(override_res["ok"])
        self.assertTrue(override_res["cooldown_overridden"])

        # Applicant 2 should now be eligible immediately to retake
        el_overridden = examination.get_exam_eligibility(self.applicant_2)
        self.assertTrue(el_overridden["eligible"])
        self.assertEqual(el_overridden["reason"], "READY")

    # 9. ABAC Security Invariants
    def test_exam_abac_security_invariants(self):
        # Applicant cannot call admin endpoints
        with self.assertRaises(PermissionError):
            examination.admin_list_attempts(self.applicant_1)

        with self.assertRaises(PermissionError):
            examination.admin_override_cooldown(self.applicant_1, self.applicant_2["id"])

        # Reviewer cannot call exam admin endpoints
        with self.assertRaises(PermissionError):
            examination.admin_list_attempts(self.reviewer)


if __name__ == "__main__":
    unittest.main()
