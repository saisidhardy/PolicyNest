"""Comprehensive verification test suite for Milestone 1:
Architecture, Enterprise Security, 11-Role ABAC, Staff Lifecycle, and Database Migrations.

Run with: python -m unittest test_milestone1_security.py
"""
import json
import os
import secrets
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

# Force test configuration
os.environ["POLICYNEST_SKIP_DOTENV"] = "1"
os.environ["JWT_SECRET"] = "milestone1-testing-super-secret-key-32chars"
os.environ["POLICYNEST_ENV"] = "sandbox"

import auth
import config
import mfa
import migrations
import policy


class Milestone1SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m1.sqlite3"
        os.environ["POLICYNEST_DB_PATH"] = str(self.db_path)
        auth.DB_PATH = self.db_path
        auth.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    # =================================================================
    # 1. DATABASE MIGRATIONS & SCHEMA INTEGRITY
    # =================================================================
    def test_migrations_idempotency_and_tables(self):
        with auth._db() as db:
            # Check migrations table
            rows = db.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC").fetchall()
            versions = [r[0] for r in rows]
            self.assertEqual(versions, [1, 2, 3])

            # Check that re-running migrations does not error and applies 0 new
            applied = migrations.run_migrations(db)
            self.assertEqual(applied, 0)

            # Check core tables exist
            tables = {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            required_tables = {
                "users",
                "application_snapshots",
                "refresh_tokens",
                "reset_tokens",
                "cases",
                "appeals",
                "audit_events",
                "review_notes",
                "assignment_history",
                "applications",
                "timeline",
                "notifications",
                "ai_daily_usage",
                "staff_profiles",
                "staff_invitations",
                "role_audit_events",
                "csrf_secrets",
                "document_records",
                "verification_results",
                "cross_document_checks",
                "fraud_cases",
                "training_modules",
                "training_progress",
                "exam_attempts",
                "certificates",
            }
            self.assertTrue(required_tables.issubset(tables), f"Missing tables: {required_tables - tables}")

    # =================================================================
    # 2. 11-ROLE ABAC ENGINE (NIST SP 800-162)
    # =================================================================
    def test_all_eleven_roles_recognized(self):
        expected_roles = {
            "applicant",
            "reviewer",
            "senior_reviewer",
            "operations",
            "compliance_officer",
            "fraud_investigator",
            "training_admin",
            "exam_admin",
            "certificate_admin",
            "tech_admin",
            "auditor",
        }
        self.assertTrue(expected_roles.issubset(policy.PLATFORM_ROLES))

    def test_horizontal_escalation_prevention(self):
        # Applicant 1 cannot access Applicant 2's application or draft
        app_res = {"applicant_id": 101, "reviewer_id": 201, "status": "DRAFT", "sensitivity": "applicant"}
        self.assertTrue(policy.allows({"id": 101, "role": "applicant"}, "application.read", app_res))
        self.assertFalse(policy.allows({"id": 102, "role": "applicant"}, "application.read", app_res))
        self.assertFalse(policy.allows({"id": 102, "role": "applicant"}, "application.save", app_res))

        # Reviewer 201 can review, Reviewer 202 cannot review unassigned case
        self.assertTrue(policy.allows({"id": 201, "role": "reviewer"}, "review.decide", app_res))
        self.assertFalse(policy.allows({"id": 202, "role": "reviewer"}, "review.decide", app_res))

    def test_vertical_escalation_prevention(self):
        app_res = {"applicant_id": 101, "reviewer_id": 201, "status": "DRAFT", "sensitivity": "applicant"}

        # Applicant cannot decide reviews or manage staff
        self.assertFalse(policy.allows({"id": 101, "role": "applicant"}, "review.decide", app_res))
        self.assertFalse(policy.allows({"id": 101, "role": "applicant"}, "staff.provision", {"sensitivity": "system"}))
        self.assertFalse(policy.allows({"id": 101, "role": "applicant"}, "fraud.hold_manage", app_res))

        # Reviewer cannot manage staff or issue certificates
        self.assertFalse(policy.allows({"id": 201, "role": "reviewer"}, "staff.provision", {"sensitivity": "system"}))
        self.assertFalse(policy.allows({"id": 201, "role": "reviewer"}, "certificate.issue", app_res))

    def test_tech_admin_has_no_unrestricted_applicant_document_access(self):
        # Non-negotiable Principle: tech_admin never receives unrestricted applicant-document access
        sensitive_doc = {"applicant_id": 101, "reviewer_id": 201, "status": "IN_REVIEW", "sensitivity": "reviewer_only"}
        self.assertFalse(policy.allows({"id": 999, "role": "tech_admin"}, "application.read", sensitive_doc))

    def test_auditor_is_strictly_read_only(self):
        auditor = {"id": 888, "role": "auditor"}
        self.assertTrue(policy.allows(auditor, "audit.read", {"sensitivity": "applicant"}))
        self.assertTrue(policy.allows(auditor, "reports.read", {"sensitivity": "applicant"}))

        # Mutating actions are strictly denied
        for forbidden in ["application.save", "review.decide", "staff.provision", "appeal.resolve", "certificate.issue"]:
            self.assertFalse(policy.allows(auditor, forbidden, {"sensitivity": "applicant"}))

    def test_data_sensitivity_boundaries(self):
        applicant = {"id": 101, "role": "applicant"}
        reviewer = {"id": 201, "role": "reviewer"}
        fraud_inv = {"id": 301, "role": "fraud_investigator"}

        fraud_res = {"applicant_id": 101, "reviewer_id": 201, "status": "IN_REVIEW", "sensitivity": "restricted_fraud"}

        # Neither applicant nor standard reviewer can see fraud-restricted data
        self.assertFalse(policy.allows(applicant, "application.read", fraud_res))
        self.assertFalse(policy.allows(reviewer, "application.read", fraud_res))

        # Fraud investigator is allowed
        self.assertTrue(policy.allows(fraud_inv, "fraud.case_read", fraud_res))

    # =================================================================
    # 3. AUTHENTICATION, PASSWORD CONTROLS & LOCKOUT
    # =================================================================
    def test_password_length_policies(self):
        # Minimum 12 characters
        with self.assertRaises(ValueError) as ctx:
            auth.register("test@example.com", "short-pass", "Short Password")
        self.assertEqual(str(ctx.exception), "invalid_registration")

        # Valid password (>= 12 chars)
        user = auth.register("valid@example.com", "strong-password-1234", "Valid User")
        self.assertEqual(user["role"], "applicant")

    def test_public_registration_strictly_forces_applicant_role(self):
        # Public registration must never allow a client to register as reviewer or admin
        user = auth.register("sneaky@example.com", "secret-password-123", "Sneaky User")
        self.assertEqual(user["role"], "applicant")

    def test_anti_account_enumeration(self):
        # Non-existent user returns invalid_credentials
        with self.assertRaises(ValueError) as ctx1:
            auth.login("nonexistent@example.com", "random-password-123")
        self.assertEqual(str(ctx1.exception), "invalid_credentials")

        # Existing user with wrong password returns the EXACT SAME error
        auth.register("existing@example.com", "correct-password-123", "Existing User")
        with self.assertRaises(ValueError) as ctx2:
            auth.login("existing@example.com", "wrong-password-999")
        self.assertEqual(str(ctx2.exception), "invalid_credentials")

    def test_account_lockout_after_5_failures(self):
        email = "lockout@example.com"
        auth.register(email, "super-secure-password", "Lockout Target")

        # 4 consecutive bad attempts
        for _ in range(4):
            with self.assertRaises(ValueError) as ctx:
                auth.login(email, "wrong-password")
            self.assertEqual(str(ctx.exception), "invalid_credentials")

        # 5th attempt triggers lockout
        with self.assertRaises(ValueError) as ctx:
            auth.login(email, "wrong-password")
        self.assertEqual(str(ctx.exception), "invalid_credentials")

        # 6th attempt is locked out
        with self.assertRaises(ValueError) as ctx:
            auth.login(email, "super-secure-password")
        self.assertEqual(str(ctx.exception), "account_locked")

    # =================================================================
    # 4. CONTROLLED STAFF PROVISIONING & LIFECYCLE
    # =================================================================
    def test_staff_provisioning_workflow(self):
        admin_user = {"id": 1, "role": "tech_admin"}

        # Provision a senior reviewer
        reviewer = auth.provision_staff(
            actor=admin_user,
            email="senior.rev@policynest.com",
            role="senior_reviewer",
            department="Underwriting Operations",
            employee_id="PN-REV-001",
            display_name="Senior Reviewer Sarah",
        )
        self.assertEqual(reviewer["role"], "senior_reviewer")
        self.assertTrue(reviewer["must_reset_password"])
        self.assertIn("temporary_password", reviewer)

        # Login with temporary password works
        logged_in = auth.login("senior.rev@policynest.com", reviewer["temporary_password"])
        self.assertEqual(logged_in["role"], "senior_reviewer")

    def test_staff_invitation_and_acceptance(self):
        admin_user = {"id": 1, "role": "tech_admin"}

        # Send invite
        invitation = auth.invite_staff(
            actor=admin_user,
            email="fraud.analyst@policynest.com",
            role="fraud_investigator",
            department="Fraud Risk Unit",
        )
        self.assertEqual(invitation["email"], "fraud.analyst@policynest.com")
        self.assertTrue(invitation["invitation_token"])

        # Accept invite and set permanent password
        accepted = auth.accept_staff_invite(
            invitation_token=invitation["invitation_token"],
            password="fraud-secure-password-123",
            display_name="Investigator Irene",
        )
        self.assertEqual(accepted["role"], "fraud_investigator")
        self.assertFalse(accepted["must_reset_password"])

        # Invitation cannot be reused
        with self.assertRaises(ValueError) as ctx:
            auth.accept_staff_invite(
                invitation_token=invitation["invitation_token"],
                password="another-password-123",
            )
        self.assertEqual(str(ctx.exception), "invalid_or_expired_invitation")

    def test_staff_role_change_revokes_sessions_and_audits(self):
        admin_user = {"id": 1, "role": "tech_admin"}
        staff = auth.provision_staff(
            actor=admin_user,
            email="ops.user@policynest.com",
            role="operations",
        )
        # Issue token for staff
        token1 = auth.issue(staff)
        auth.authenticate(f"Bearer {token1}")

        # Update role to compliance_officer
        updated = auth.update_staff_role(
            actor=admin_user,
            target_user_id=staff["id"],
            new_role="compliance_officer",
            reason="Promoted to Compliance",
        )
        self.assertEqual(updated["role"], "compliance_officer")

        # Old token is now invalid due to token_version bump
        with self.assertRaises(ValueError):
            auth.authenticate(f"Bearer {token1}")

        # Role change is logged in role_audit_events
        with auth._db() as db:
            log = db.execute("SELECT * FROM role_audit_events WHERE target_user_id=?", (staff["id"],)).fetchall()
            self.assertEqual(len(log), 2)  # Provisioned + Role changed
            self.assertEqual(log[1]["old_role"], "operations")
            self.assertEqual(log[1]["new_role"], "compliance_officer")

    def test_staff_account_suspension(self):
        admin_user = {"id": 1, "role": "tech_admin"}
        staff = auth.provision_staff(
            actor=admin_user,
            email="suspended.user@policynest.com",
            role="reviewer",
        )
        # Suspend staff account
        auth.set_staff_status(admin_user, staff["id"], "suspended", "Security review hold")

        # Login fails with account_suspended
        with self.assertRaises(ValueError) as ctx:
            auth.login("suspended.user@policynest.com", staff["temporary_password"])
        self.assertEqual(str(ctx.exception), "account_suspended")

    # =================================================================
    # 5. MULTI-FACTOR AUTHENTICATION (TOTP RFC 6238)
    # =================================================================
    def test_mfa_setup_and_login_challenge(self):
        admin_user = {"id": 1, "role": "tech_admin"}
        staff = auth.provision_staff(
            actor=admin_user,
            email="mfa.staff@policynest.com",
            role="compliance_officer",
        )

        # Setup MFA
        setup_data = auth.setup_mfa(staff)
        self.assertTrue(setup_data["secret"])
        self.assertTrue(setup_data["totp_uri"].startswith("otpauth://totp/PolicyNest:mfa.staff@policynest.com"))
        self.assertEqual(len(setup_data["recovery_codes"]), 8)

        # Verify and activate MFA with correct TOTP code
        code = mfa.generate_totp_code(setup_data["secret"])
        verify_res = auth.verify_and_enable_mfa(staff, code)
        self.assertTrue(verify_res["mfa_enabled"])

        # Login without code raises mfa_required
        with self.assertRaises(ValueError) as ctx:
            auth.login("mfa.staff@policynest.com", staff["temporary_password"])
        self.assertEqual(str(ctx.exception), "mfa_required")

        # Login with correct code succeeds
        now_code = mfa.generate_totp_code(setup_data["secret"])
        logged_in = auth.login("mfa.staff@policynest.com", staff["temporary_password"], mfa_code=now_code)
        self.assertEqual(logged_in["email"], "mfa.staff@policynest.com")

        # Login with recovery code works and consumes the recovery code
        rec_code = setup_data["recovery_codes"][0]
        rec_login = auth.login("mfa.staff@policynest.com", staff["temporary_password"], mfa_code=rec_code)
        self.assertEqual(rec_login["email"], "mfa.staff@policynest.com")

        # Recovery code cannot be reused
        with self.assertRaises(ValueError) as ctx:
            auth.login("mfa.staff@policynest.com", staff["temporary_password"], mfa_code=rec_code)
        self.assertEqual(str(ctx.exception), "invalid_mfa_code")

    # =================================================================
    # 6. ANTI-CSRF TOKEN PROTECTION
    # =================================================================
    def test_csrf_token_generation_and_verification(self):
        user = auth.register("csrf.test@example.com", "csrf-strong-password", "CSRF User")
        token = auth.get_csrf_token(user)
        self.assertTrue(token and len(token) >= 24)

        # Token matches
        self.assertTrue(auth.verify_csrf(user, token))

        # Tampered or empty token fails
        self.assertFalse(auth.verify_csrf(user, "wrong-csrf-token"))
        self.assertFalse(auth.verify_csrf(user, ""))
        self.assertFalse(auth.verify_csrf({"id": 9999}, token))


if __name__ == "__main__":
    unittest.main(verbosity=2)
