"""Comprehensive verification test suite for Milestone 2:
Applicant Account, Durable Application Persistence, Concurrency Control,
Normalized Status Model, Centralized Next-Action Resolver, and Applicant Dashboard.

Run with: python -m unittest test_milestone2_persistence.py
"""
import json
import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path

os.environ["POLICYNEST_SKIP_DOTENV"] = "1"
os.environ["JWT_SECRET"] = "milestone2-testing-super-secret-key-32chars"
os.environ["POLICYNEST_ENV"] = "sandbox"

import application as app_module
import auth
import next_action
import policy
import portal
import profile as prof_module
import status_model


class Milestone2PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m2.sqlite3"
        os.environ["POLICYNEST_DB_PATH"] = str(self.db_path)
        auth.DB_PATH = self.db_path
        auth.init_db()
        portal.init()

        # Register test applicant
        self.applicant = auth.register("rahul.verma@example.com", "Password@123456", "Rahul Verma")
        self.applicant_token = auth.issue(self.applicant)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =================================================================
    # 1. APPLICANT PROFILE & ACCOUNT MANAGEMENT
    # =================================================================
    def test_applicant_profile_retrieval_and_minimization(self):
        profile = prof_module.get_applicant_profile(self.applicant)
        self.assertEqual(profile["email"], "rahul.verma@example.com")
        self.assertEqual(profile["display_name"], "Rahul Verma")
        self.assertEqual(profile["role"], "applicant")
        # No full identity numbers or sensitive bank details in profile
        for forbidden_key in ["pan", "aadhaar", "bank_account", "password", "password_hash"]:
            self.assertNotIn(forbidden_key, profile)

    def test_applicant_profile_updating_and_validations(self):
        # Update contact and location info
        updated = prof_module.update_applicant_profile(
            self.applicant,
            {
                "mobile": "9876543210",
                "language": "hi",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "notification_preferences": {"email": True, "in_app": True, "sms": True},
            },
        )
        self.assertEqual(updated["mobile_masked"], "••••••3210")
        self.assertEqual(updated["language"], "hi")
        self.assertEqual(updated["city"], "Lucknow")
        self.assertEqual(updated["state"], "Uttar Pradesh")
        self.assertEqual(updated["pincode"], "226001")
        self.assertTrue(updated["notification_preferences"]["sms"])

        # Invalid mobile number rejected
        with self.assertRaises(ValueError) as ctx:
            prof_module.update_applicant_profile(self.applicant, {"mobile": "12345"})
        self.assertEqual(str(ctx.exception), "invalid_mobile")

        # Invalid pincode rejected
        with self.assertRaises(ValueError) as ctx:
            prof_module.update_applicant_profile(self.applicant, {"pincode": "ABC1234"})
        self.assertEqual(str(ctx.exception), "invalid_pincode")

    def test_self_service_password_change_and_session_revocation(self):
        # Existing token is valid
        auth.authenticate(f"Bearer {self.applicant_token}")

        # Wrong current password fails
        with self.assertRaises(ValueError) as ctx:
            prof_module.change_applicant_password(self.applicant, "WrongCurrentPassword", "NewStrongPassword123")
        self.assertEqual(str(ctx.exception), "invalid_current_password")

        # Successful password change
        res = prof_module.change_applicant_password(self.applicant, "Password@123456", "NewStrongPassword123")
        self.assertTrue(res["ok"])

        # Old token is immediately invalidated across all devices
        with self.assertRaises(ValueError):
            auth.authenticate(f"Bearer {self.applicant_token}")

        # Login with new password succeeds
        logged_in = auth.login("rahul.verma@example.com", "NewStrongPassword123")
        self.assertEqual(logged_in["email"], "rahul.verma@example.com")

    def test_sign_out_all_sessions(self):
        token = auth.issue(self.applicant)
        auth.authenticate(f"Bearer {token}")

        res = prof_module.sign_out_all_sessions(self.applicant)
        self.assertTrue(res["ok"])

        with self.assertRaises(ValueError):
            auth.authenticate(f"Bearer {token}")

    def test_privacy_data_export_and_deletion_request(self):
        # Export
        export_data = prof_module.export_applicant_data(self.applicant)
        self.assertEqual(export_data["export_metadata"]["platform"], "PolicyNest POSP Onboarding")
        self.assertIn("user_profile", export_data)
        self.assertIn("timeline_events", export_data)

        # Deletion request
        del_res = prof_module.request_account_deletion(self.applicant, reason="User requested erasure")
        self.assertTrue(del_res["request_id"].startswith("DEL-"))
        self.assertEqual(del_res["status"], "REQUESTED")

    # =================================================================
    # 2. APPLICATION MODEL, REFERENCE ID & AUTOSAVE CONCURRENCY
    # =================================================================
    def test_application_creation_and_reference_id_format(self):
        app = app_module.get_or_create_application(self.applicant)
        self.assertTrue(app["reference"].startswith("PN-2026-"))
        self.assertEqual(app["status"], "DRAFT")
        self.assertEqual(app["version"], 1)

        # Calling again returns the exact same application (no duplicates)
        app2 = app_module.get_or_create_application(self.applicant)
        self.assertEqual(app["id"], app2["id"])
        self.assertEqual(app["reference"], app2["reference"])

    def test_autosave_and_optimistic_concurrency_locking(self):
        app = app_module.get_or_create_application(self.applicant)
        cur_version = app["version"]

        # Device 1 saves draft with version 1
        save1 = app_module.save_draft(
            self.applicant,
            {
                "version": cur_version,
                "stage": "Basics",
                "section": "personal",
                "page": 2,
                "details": {"name": "Rahul Verma", "dob": "1995-08-15", "state": "Delhi", "city": "New Delhi"},
                "resume_position": {"stage": "Basics", "section": "personal", "page": 2},
            },
        )
        self.assertTrue(save1["ok"])
        self.assertEqual(save1["version"], 2)

        # Device 2 attempts to save with stale version 1 -> Must raise conflict_detected
        with self.assertRaises(ValueError) as ctx:
            app_module.save_draft(
                self.applicant,
                {
                    "version": cur_version,  # Stale!
                    "stage": "Basics",
                    "section": "address",
                    "page": 1,
                    "details": {"name": "Rahul V."},
                },
            )
        self.assertEqual(str(ctx.exception), "conflict_detected")

        # Device 2 saves with up-to-date version 2 -> Succeeds
        save2 = app_module.save_draft(
            self.applicant,
            {
                "version": 2,
                "stage": "Documents",
                "section": "documents",
                "page": 1,
                "resume_position": {"stage": "Documents", "section": "documents", "doc_slot": "PAN"},
            },
        )
        self.assertEqual(save2["version"], 3)

    def test_exact_resume_position(self):
        app = app_module.get_or_create_application(self.applicant)
        app_module.save_draft(
            self.applicant,
            {
                "version": app["version"],
                "stage": "Documents",
                "section": "documents",
                "page": 1,
                "resume_position": {"stage": "Documents", "section": "documents", "doc_slot": "AADHAAR_FRONT"},
            },
        )

        resume = app_module.get_resume_position(self.applicant)
        self.assertEqual(resume["stage"], "Documents")
        self.assertEqual(resume["section"], "documents")
        self.assertEqual(resume["doc_slot"], "AADHAAR_FRONT")
        self.assertEqual(resume["destination"], "#documents")

    def test_application_submission_validations(self):
        app = app_module.get_or_create_application(self.applicant)

        # Incomplete personal details fails submission
        with self.assertRaises(ValueError) as ctx:
            app_module.submit_application(self.applicant)
        self.assertEqual(str(ctx.exception), "incomplete_personal_details")

        # Fill personal details but missing documents
        app_module.save_draft(
            self.applicant,
            {
                "version": app["version"],
                "details": {"name": "Rahul Verma", "dob": "1995-08-15", "state": "Delhi"},
            },
        )
        with self.assertRaises(ValueError) as ctx:
            app_module.submit_application(self.applicant)
        self.assertTrue(str(ctx.exception).startswith("missing_required_document_"))

        # Provide all required documents
        app2 = app_module.get_application(self.applicant)
        docs = {
            slot: {"status": "uploaded", "version": 1}
            for slot in ["PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK"]
        }
        app_module.save_draft(
            self.applicant,
            {
                "version": app2["version"],
                "progress": {"documents": docs},
            },
        )

        # Submission now succeeds
        submit_res = app_module.submit_application(self.applicant)
        self.assertTrue(submit_res["ok"])
        self.assertEqual(submit_res["status"], "SUBMITTED")

    # =================================================================
    # 3. NORMALIZED STATUS MODEL & TRANSITION VALIDATION
    # =================================================================
    def test_status_metadata_and_localization(self):
        # English metadata
        en_info = status_model.get_status_info("KYC_APPROVED", lang="en")
        self.assertEqual(en_info["label"], "Documents Verified")
        self.assertEqual(en_info["badge_color"], "green")
        self.assertTrue(en_info["action_required"])

        # Hindi metadata
        hi_info = status_model.get_status_info("KYC_APPROVED", lang="hi")
        self.assertEqual(hi_info["label"], "दस्तावेज़ सत्यापित")
        self.assertEqual(hi_info["badge_color"], "green")

    def test_status_transition_rules(self):
        # Valid: DRAFT -> IN_PROGRESS -> SUBMITTED -> IN_REVIEW
        self.assertTrue(status_model.validate_transition("DRAFT", "IN_PROGRESS"))
        self.assertTrue(status_model.validate_transition("IN_PROGRESS", "SUBMITTED"))
        self.assertTrue(status_model.validate_transition("SUBMITTED", "IN_REVIEW"))

        # Invalid: DRAFT -> CERTIFIED directly is impossible
        self.assertFalse(status_model.validate_transition("DRAFT", "CERTIFIED"))
        self.assertFalse(status_model.validate_transition("REJECTED", "CERTIFIED"))

    # =================================================================
    # 4. CENTRALIZED NEXT-ACTION RESOLVER
    # =================================================================
    def test_next_action_incomplete_basics(self):
        app = {"status": "DRAFT", "details": {}, "progress": {}}
        action = next_action.resolve_next_action(app)
        self.assertEqual(action["reason_code"], "INCOMPLETE_BASICS")
        self.assertEqual(action["stage"], "Basics")
        self.assertEqual(action["priority"], "action-required")

    def test_next_action_missing_documents(self):
        app = {
            "status": "DRAFT",
            "details": {"name": "Rahul Verma", "dob": "1995-08-15", "state": "Delhi", "city": "Delhi"},
            "progress": {"documents": {}},
        }
        action = next_action.resolve_next_action(app)
        self.assertEqual(action["reason_code"], "DOCUMENTS_MISSING")
        self.assertEqual(action["stage"], "Documents")
        self.assertEqual(action["destination"], "#documents")

    def test_next_action_corrections_required(self):
        app = {
            "status": "NEEDS_MORE_INFO",
            "progress": {
                "documents": {
                    "PAN": {"status": "action_required", "issues": ["IMAGE_BLURRY"]},
                    "CLASS10": {"status": "action_required", "issues": ["DOB_MISMATCH"]},
                }
            },
        }
        action = next_action.resolve_next_action(app)
        self.assertEqual(action["reason_code"], "CORRECTIONS_REQUIRED")
        self.assertEqual(action["priority"], "urgent")
        self.assertIn("2 document issues", action["label"])

    def test_next_action_training_and_exam(self):
        # 5 hours logged in training
        app_training = {
            "status": "KYC_APPROVED",
            "progress": {"training": {"hours": 5, "modules": ["m1", "m2"]}},
        }
        action1 = next_action.resolve_next_action(app_training)
        self.assertEqual(action1["reason_code"], "TRAINING_INCOMPLETE")
        self.assertEqual(action1["stage"], "Training")
        self.assertIn("5/15 Hours", action1["label"])

        # 15 hours completed -> Exam Ready
        app_exam = {
            "status": "TRAINING_COMPLETE",
            "progress": {"training": {"hours": 15}},
        }
        action2 = next_action.resolve_next_action(app_exam)
        self.assertEqual(action2["reason_code"], "EXAM_READY")
        self.assertEqual(action2["stage"], "Exam")

    def test_next_action_certified(self):
        app_cert = {
            "status": "CERTIFIED",
            "progress": {"certificate": {"code": "PN-CERT-12345"}},
        }
        action = next_action.resolve_next_action(app_cert)
        self.assertEqual(action["reason_code"], "CERTIFICATE_READY")
        self.assertEqual(action["destination"], "#certificate")

    # =================================================================
    # 5. APPLICANT DASHBOARD AGGREGATOR
    # =================================================================
    def test_applicant_dashboard_payload(self):
        dash = app_module.get_applicant_dashboard(self.applicant, lang="en")
        self.assertIn("Welcome back, Rahul Verma!", dash["greeting"])
        self.assertTrue(dash["reference"].startswith("PN-2026-"))
        self.assertIn("status", dash)
        self.assertEqual(len(dash["six_stage_progress"]), 6)
        self.assertIn("primary_next_action", dash)
        self.assertIn("document_checklist", dash)
        self.assertEqual(len(dash["document_checklist"]), 5)
        self.assertIn("resume_position", dash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
