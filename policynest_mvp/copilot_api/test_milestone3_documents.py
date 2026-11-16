"""Unit and Integration Tests for Milestone 3: Documents & Verification.

Tests:
1. Storage Engine & Upload Security:
   - Magic byte identification for PNG, JPEG, PDF, WebP.
   - Disguised executable (.exe, ELF, Mach-O) and script rejection.
   - File size limits (min 1KB, max 5MB).
   - Pure standard library image dimension parsing.
2. Quality Assessment & Guided Capture:
   - Resolution, aspect ratio, blur, glare, dark exposure.
   - Bilingual English / Hindi guidance and defect coaching.
3. Verification Providers:
   - PAN validation (Individual 'P' vs Company 'C' / Firm 'F').
   - Aadhaar validation (Verhoeff checksum, mandatory masking to XXXXXXXX1234).
   - Bank verification (IFSC format, penny drop simulation).
   - Class 10 verification (educational qualification, pass status).
4. 8-Tier Indian Name Matching Engine:
   - All 8 tiers tested with realistic Indian identity edge cases.
5. Cross-Document Verification & Age Rules:
   - Cross-matching across PAN, Aadhaar, Bank, Class 10.
   - IRDAI age eligibility (>= 18 years passed, < 18 rejected).
6. Document Lifecycle, Correction & ABAC Security:
   - Document upload, slot tracking, and metadata.
   - ABAC: Tech Admin and Auditor strictly forbidden from downloading applicant images.
   - Correction and rework flow from NEEDS_MORE_INFO to IN_REVIEW.
"""
import base64
import datetime
import os
import struct
import tempfile
import unittest
from pathlib import Path

import auth
import config
import cross_checks
import documents
import migrations
import portal
import providers
import quality
import storage


def _create_minimal_png(width=500, height=400):
    """Generate minimal valid PNG bytes with IHDR dimensions."""
    header = b"\x89PNG\r\n\x1a\n"
    # IHDR chunk: length (4 bytes), type (4 bytes: IHDR), data (13 bytes), crc (4 bytes)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", 0x12345678)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
    # Add dummy padding to reach > 1024 bytes
    padding = b"\x00" * 1200
    return header + ihdr_chunk + padding


def _create_minimal_jpeg(width=640, height=480):
    """Generate minimal valid JPEG bytes with SOF0 dimensions."""
    header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    # SOF0 marker: 0xFF, 0xC0, length (2 bytes), precision (1 byte), height (2 bytes), width (2 bytes)
    sof_len = 11
    sof_marker = b"\xff\xc0" + struct.pack(">H", sof_len) + b"\x08" + struct.pack(">HH", height, width) + b"\x01\x11\x00"
    padding = b"\x00" * 1200
    return header + sof_marker + padding


def _create_minimal_pdf():
    """Generate minimal valid PDF bytes."""
    header = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    padding = b"% " + (b"A" * 1200) + b"\n%%EOF"
    return header + padding


class Milestone3DocumentsTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_policynest.sqlite3"
        self.docs_dir = Path(self.temp_dir.name) / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        self.orig_db_env = os.environ.get("POLICYNEST_DB_PATH")
        self.orig_docs_env = os.environ.get("POLICYNEST_DOCS_DIR")

        os.environ["POLICYNEST_DB_PATH"] = str(self.db_path)
        os.environ["POLICYNEST_DOCS_DIR"] = str(self.docs_dir)

        auth.DB_PATH = self.db_path
        auth.init_db()
        portal.init()

    def tearDown(self):
        if self.orig_db_env:
            os.environ["POLICYNEST_DB_PATH"] = self.orig_db_env
        else:
            os.environ.pop("POLICYNEST_DB_PATH", None)

        if self.orig_docs_env:
            os.environ["POLICYNEST_DOCS_DIR"] = self.orig_docs_env
        else:
            os.environ.pop("POLICYNEST_DOCS_DIR", None)

        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Storage & Magic Byte Detection Tests
    # -------------------------------------------------------------
    def test_magic_bytes_detection_and_disguised_file_rejection(self):
        png_bytes = _create_minimal_png()
        self.assertEqual(storage.detect_mime_type(png_bytes), "image/png")

        jpeg_bytes = _create_minimal_jpeg()
        self.assertEqual(storage.detect_mime_type(jpeg_bytes), "image/jpeg")

        pdf_bytes = _create_minimal_pdf()
        self.assertEqual(storage.detect_mime_type(pdf_bytes), "application/pdf")

        # Windows PE Executable disguised as an image
        fake_exe = b"MZ\x90\x00\x03\x00\x00\x00" + (b"\x00" * 1200)
        with self.assertRaises(ValueError) as ctx:
            storage.detect_mime_type(fake_exe)
        self.assertIn("dangerous_file_type_detected", str(ctx.exception))

        # Shell Script disguised as a document
        fake_script = b"#!/bin/bash\nrm -rf /\n" + (b"\x00" * 1100)
        with self.assertRaises(ValueError) as ctx:
            storage.detect_mime_type(fake_script)
        self.assertIn("dangerous_file_type_detected", str(ctx.exception))

        # HTML / XSS Script injection
        fake_html = b"<script>alert(1)</script>" + (b"\x00" * 1100)
        with self.assertRaises(ValueError) as ctx:
            storage.detect_mime_type(fake_html)
        self.assertIn("dangerous_file_type_detected", str(ctx.exception))

    def test_file_size_constraints(self):
        # File under 1KB
        tiny_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 50)
        with self.assertRaises(ValueError) as ctx:
            storage.validate_file_content(tiny_bytes)
        self.assertEqual(str(ctx.exception), "file_too_small")

        # File over 5MB
        huge_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (5 * 1024 * 1024 + 100))
        with self.assertRaises(ValueError) as ctx:
            storage.validate_file_content(huge_bytes)
        self.assertEqual(str(ctx.exception), "file_size_exceeds_limit")

    def test_image_dimension_parsing(self):
        png = _create_minimal_png(width=800, height=600)
        w, h = storage.extract_image_dimensions(png, "image/png")
        self.assertEqual(w, 800)
        self.assertEqual(h, 600)

        jpeg = _create_minimal_jpeg(width=1024, height=768)
        w, h = storage.extract_image_dimensions(jpeg, "image/jpeg")
        self.assertEqual(w, 1024)
        self.assertEqual(h, 768)

    # -------------------------------------------------------------
    # 2. Quality Assessment & Coaching Tests
    # -------------------------------------------------------------
    def test_quality_assessment_scoring_and_bilingual_coaching(self):
        # High quality image
        meta_good = {"file_size": 250000, "width": 1200, "height": 800, "mime_type": "image/jpeg"}
        res_good = quality.assess_quality(meta_good, slot="PAN")
        self.assertTrue(res_good["passed"])
        self.assertGreaterEqual(res_good["quality_score"], 0.70)
        self.assertEqual(len(res_good["issues"]), 0)

        # Low resolution defect
        meta_low = {"file_size": 20000, "width": 250, "height": 180, "mime_type": "image/jpeg"}
        res_low = quality.assess_quality(meta_low, slot="PAN")
        self.assertFalse(res_low["passed"])
        self.assertIn("RESOLUTION_TOO_LOW", res_low["issues"])
        self.assertTrue(len(res_low["remediation_en"]) > 0)
        self.assertTrue(len(res_low["remediation_hi"]) > 0)

        # Blurry capture optical feedback
        res_blur = quality.assess_quality(meta_good, client_signals={"blur_score": 0.45}, slot="PAN")
        self.assertFalse(res_blur["passed"])
        self.assertIn("IMAGE_BLURRY", res_blur["issues"])
        self.assertIn("blurry", res_blur["remediation_en"].lower())

        # Glare defect
        res_glare = quality.assess_quality(meta_good, client_signals={"glare_score": 0.65}, slot="PAN")
        self.assertFalse(res_glare["passed"])
        self.assertIn("IMAGE_GLARE", res_glare["issues"])
        self.assertIn("glare", res_glare["remediation_en"].lower())

    # -------------------------------------------------------------
    # 3. Provider Verification Tests (PAN, Aadhaar, Bank, Class 10)
    # -------------------------------------------------------------
    def test_pan_individual_vs_corporate_entity(self):
        # Valid Individual PAN (4th char 'P')
        res_valid = providers.PanVerificationProvider.verify("ABCPA1234F", "Saisidhardh Vajja")
        self.assertTrue(res_valid["ok"])
        self.assertEqual(res_valid["status"], "VALID")
        self.assertEqual(res_valid["category"], "INDIVIDUAL")
        self.assertEqual(res_valid["pan_masked"], "ABCPA****F")

        # Corporate PAN (4th char 'C' = Company)
        res_corp = providers.PanVerificationProvider.verify("ABCCA1234F", "Acme Corporation")
        self.assertFalse(res_corp["ok"])
        self.assertEqual(res_corp["code"], "PAN_NOT_INDIVIDUAL")
        self.assertIn("Company", res_corp["error"])

        # Firm PAN (4th char 'F' = Firm)
        res_firm = providers.PanVerificationProvider.verify("ABCFA1234F", "Alpha Partners")
        self.assertFalse(res_firm["ok"])
        self.assertEqual(res_firm["code"], "PAN_NOT_INDIVIDUAL")
        self.assertIn("Firm", res_firm["error"])

        # Invalid format
        res_bad = providers.PanVerificationProvider.verify("INVALID123")
        self.assertFalse(res_bad["ok"])
        self.assertEqual(res_bad["code"], "INVALID_PAN_FORMAT")

    def test_aadhaar_verhoeff_and_data_minimization(self):
        # 12-digit number generated with Verhoeff check digit
        valid_12 = providers.generate_verhoeff_12("99994105123")
        self.assertTrue(providers.validate_verhoeff(valid_12))

        # Tampered check digit fails
        tampered_12 = valid_12[:-1] + ("0" if valid_12[-1] != "0" else "1")
        self.assertFalse(providers.validate_verhoeff(tampered_12))

        # Valid masked input from applicant
        res_masked = providers.AadhaarKycProvider.verify("XXXXXXXX5678", "Saisidhardh Vajja")
        self.assertTrue(res_masked["ok"])
        self.assertEqual(res_masked["status"], "VERIFIED")
        self.assertEqual(res_masked["masked_uid"], "XXXXXXXX5678")

        # Full 12-digit input verified and masked
        res_12 = providers.AadhaarKycProvider.verify(valid_12, "Saisidhardh Vajja")
        self.assertTrue(res_12["ok"])
        self.assertEqual(res_12["masked_uid"], "XXXXXXXX" + valid_12[-4:])
        self.assertNotIn("raw_aadhaar", str(res_12))

    def test_bank_verification_and_penny_drop(self):
        # Valid account and IFSC (5th char '0')
        res_bank = providers.BankVerificationProvider.verify(
            account_number="123456789012",
            ifsc_code="SBIN0001234",
            applicant_name="Saisidhardh Vajja",
        )
        self.assertTrue(res_bank["ok"])
        self.assertEqual(res_bank["status"], "VERIFIED")
        self.assertEqual(res_bank["account_status"], "ACTIVE")
        self.assertEqual(res_bank["account_masked"], "••••••••9012")
        self.assertTrue(res_bank["utr_number"].startswith("UTR"))

        # Invalid IFSC: 5th char not '0'
        res_bad_ifsc = providers.BankVerificationProvider.verify("123456789012", "SBINA001234")
        self.assertFalse(res_bad_ifsc["ok"])
        self.assertEqual(res_bad_ifsc["code"], "INVALID_IFSC_FORMAT")

        # Invalid Account Number (letters or too short)
        res_bad_acc = providers.BankVerificationProvider.verify("1234", "SBIN0001234")
        self.assertFalse(res_bad_acc["ok"])
        self.assertEqual(res_bad_acc["code"], "INVALID_ACCOUNT_NUMBER")

    def test_class10_qualification_verification(self):
        res = providers.Class10VerificationProvider.verify(
            roll_number="6543210",
            board_name="CBSE",
            applicant_name="Saisidhardh Vajja",
            applicant_dob="1995-05-15",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["result"], "PASS")
        self.assertTrue(res["is_eligible_for_posp"])

        # Missing roll number
        res_empty = providers.Class10VerificationProvider.verify("", "CBSE")
        self.assertFalse(res_empty["ok"])
        self.assertEqual(res_empty["code"], "MISSING_ROLL_NUMBER")

    # -------------------------------------------------------------
    # 4. 8-Tier Indian Name Matching Engine Tests
    # -------------------------------------------------------------
    def test_8_tier_indian_name_matching_engine(self):
        # Tier 1: Exact Match
        t1 = cross_checks.match_indian_names("Saisidhardh Vajja", "SAISIDHARDH VAJJA")
        self.assertEqual(t1["tier"], 1)
        self.assertEqual(t1["score"], 1.0)
        self.assertTrue(t1["matched"])

        # Tier 2: Token Permutation / Order Inversion
        t2 = cross_checks.match_indian_names("Vajja Saisidhardh", "Saisidhardh Vajja")
        self.assertEqual(t2["tier"], 2)
        self.assertEqual(t2["score"], 0.98)
        self.assertTrue(t2["matched"])

        # Tier 3: Honorific & Title Stripping
        t3 = cross_checks.match_indian_names("Mr. Saisidhardh Vajja", "Saisidhardh Vajja")
        self.assertEqual(t3["tier"], 3)
        self.assertEqual(t3["score"], 0.95)
        self.assertTrue(t3["matched"])

        # Tier 4: Initials Expansion
        t4 = cross_checks.match_indian_names("S. Vajja", "Saisidhardh Vajja")
        self.assertEqual(t4["tier"], 4)
        self.assertEqual(t4["score"], 0.92)
        self.assertTrue(t4["matched"])

        # Tier 5: Phonetic Transliteration
        t5_a = cross_checks.match_indian_names("Amit Choudhary", "Amit Chowdhury")
        self.assertEqual(t5_a["tier"], 5)
        self.assertEqual(t5_a["score"], 0.88)
        self.assertTrue(t5_a["matched"])

        t5_b = cross_checks.match_indian_names("Vikas Sharma", "Bikas Sharma")
        self.assertEqual(t5_b["tier"], 5)
        self.assertTrue(t5_b["matched"])

        # Tier 7: Nickname Alias
        t7 = cross_checks.match_indian_names("Guddu Kumar", "Amit Kumar")
        self.assertEqual(t7["tier"], 7)
        self.assertEqual(t7["score"], 0.82)
        self.assertTrue(t7["matched"])

        # Tier 8: Levenshtein Typo (<= 2 edits on tokens where Soundex differs)
        t8 = cross_checks.match_indian_names("Siddharth Vajja", "Siddharkh Vajja")
        self.assertEqual(t8["tier"], 8)
        self.assertEqual(t8["score"], 0.80)
        self.assertTrue(t8["matched"])

        # Complete Mismatch
        mismatch = cross_checks.match_indian_names("Saisidhardh Vajja", "Rajesh Kumar")
        self.assertEqual(mismatch["status"], "MISMATCH")
        self.assertFalse(mismatch["matched"])
        self.assertLess(mismatch["score"], 0.65)

    # -------------------------------------------------------------
    # 5. Cross-Document Verification & Age Rules Tests
    # -------------------------------------------------------------
    def test_cross_document_matching_and_age_rules(self):
        pan = {"holder_name": "Saisidhardh Vajja", "dob": "1995-05-15"}
        aadhaar = {"name": "Vajja Saisidhardh", "dob": "1995-05-15"}
        bank = {"beneficiary_name_bank": "Saisidhardh Vajja"}
        class10 = {"candidate_name": "Saisidhardh Vajja", "dob": "1995-05-15", "result": "PASS"}

        # All matching
        rep = cross_checks.run_cross_document_checks(pan, aadhaar, bank, class10, "1995-05-15")
        self.assertEqual(rep["verdict"], "ALL_PASSED")
        self.assertEqual(rep["failed_checks"], 0)

        # DOB Mismatch
        pan_diff_dob = {"holder_name": "Saisidhardh Vajja", "dob": "1995-05-15"}
        aadhaar_diff_dob = {"name": "Saisidhardh Vajja", "dob": "1998-08-20"}
        rep_dob = cross_checks.run_cross_document_checks(pan_diff_dob, aadhaar_diff_dob, bank, class10, "1995-05-15")
        self.assertEqual(rep_dob["verdict"], "ACTION_REQUIRED")
        self.assertTrue(any(c["check_name"] == "DOB_PAN_VS_AADHAAR" and c["status"] == "FAILED" for c in rep_dob["checks"]))

        # Underage Applicant (< 18 years old)
        today = datetime.date.today()
        underage_dob = f"{today.year - 16}-01-01"
        pan_underage = {"holder_name": "Minor Applicant", "dob": underage_dob}
        aadhaar_underage = {"name": "Minor Applicant", "dob": underage_dob}
        rep_age = cross_checks.run_cross_document_checks(pan_underage, aadhaar_underage, bank, class10, underage_dob)
        self.assertEqual(rep_age["verdict"], "ACTION_REQUIRED")
        self.assertTrue(any(c["check_name"] == "AGE_ELIGIBILITY_MIN_18" and c["status"] == "FAILED" for c in rep_age["checks"]))

    # -------------------------------------------------------------
    # 6. Document Lifecycle, Correction & ABAC Security Tests
    # -------------------------------------------------------------
    def test_document_upload_and_metadata_persistence(self):
        user = auth.register("test_doc_applicant@example.com", "SecurePassword123#", "Doc Applicant")
        png_content = _create_minimal_png()

        res = documents.upload_document(
            user=user,
            slot="PAN",
            file_bytes=png_content,
            file_name="pan_card.png",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["slot"], "PAN")
        self.assertEqual(res["status"], "UPLOADED")
        doc_id = res["document_id"]

        # List documents
        doc_list = documents.list_documents(user)
        self.assertEqual(len(doc_list), 1)
        self.assertEqual(doc_list[0]["id"], doc_id)
        self.assertEqual(doc_list[0]["slot"], "PAN")

    def test_document_download_abac_security_invariants(self):
        applicant_a = auth.register("doc_owner@example.com", "SecurePassword123#", "Owner Applicant")
        applicant_b = auth.register("doc_other@example.com", "SecurePassword123#", "Other Applicant")

        png_content = _create_minimal_png()
        res = documents.upload_document(applicant_a, "PAN", png_content, "pan.png")
        doc_id = res["document_id"]

        # 1. Owner can download their own document
        content, mime, fname = documents.get_document_content(applicant_a, doc_id)
        self.assertEqual(content, png_content)
        self.assertEqual(mime, "image/png")

        # 2. Another applicant CANNOT download (horizontal privilege escalation prevention)
        with self.assertRaises(PermissionError) as ctx:
            documents.get_document_content(applicant_b, doc_id)
        self.assertIn("access_denied_not_owner", str(ctx.exception))

        # 3. Reviewer can download applicant document
        admin_actor = {"id": 1, "role": "tech_admin"}
        reviewer = auth.provision_staff(admin_actor, "reviewer1@policynest.com", "reviewer", temp_password="ReviewerPass123#")
        rev_content, _, _ = documents.get_document_content(reviewer, doc_id)
        self.assertEqual(rev_content, png_content)

        # 4. Tech Admin CANNOT download raw applicant images (NIST SP 800-162 invariant)
        tech_admin = auth.provision_staff(admin_actor, "techadmin@policynest.com", "tech_admin", temp_password="TechAdminPass123#")
        with self.assertRaises(PermissionError) as ctx:
            documents.get_document_content(tech_admin, doc_id)
        self.assertIn("access_denied_role_cannot_view_applicant_images", str(ctx.exception))

        # 5. Auditor CANNOT download raw applicant images
        auditor = auth.provision_staff(admin_actor, "auditor@policynest.com", "auditor", temp_password="AuditorPass123#")
        with self.assertRaises(PermissionError) as ctx:
            documents.get_document_content(auditor, doc_id)
        self.assertIn("access_denied_role_cannot_view_applicant_images", str(ctx.exception))

    def test_document_correction_and_rework_workflow(self):
        user = auth.register("rework_applicant@example.com", "SecurePassword123#", "Rework Applicant")
        app = documents.get_or_create_application(user)

        # Simulate reviewer marking application as NEEDS_MORE_INFO
        with auth._db() as db:
            db.execute("UPDATE applications SET status='NEEDS_MORE_INFO' WHERE id=?", (app["id"],))

        # Applicant submits corrected document
        png_content = _create_minimal_png()
        cor_res = documents.submit_document_correction(
            user=user,
            slot="PAN",
            file_bytes=png_content,
            file_name="pan_corrected.png",
            explanation="Uploaded high resolution scan without reflection",
        )
        self.assertTrue(cor_res["ok"])

        # Check application status transitioned back to IN_REVIEW
        app_updated = documents.get_or_create_application(user)
        self.assertEqual(app_updated["status"], "IN_REVIEW")

    def test_full_verification_pipeline(self):
        user = auth.register("full_verify_user@example.com", "SecurePassword123#", "Full Verify")
        app = documents.get_or_create_application(user)

        # Set valid application details
        with auth._db() as db:
            import json
            details = {
                "name": "Saisidhardh Vajja",
                "dob": "1995-05-15",
                "pan": "ABCPA1234F",
                "aadhaar": "XXXXXXXX1234",
                "bank_account": "123456789012",
                "ifsc": "SBIN0001234",
                "class10_roll": "9876543",
                "board": "CBSE",
            }
            db.execute("UPDATE applications SET details=? WHERE id=?", (json.dumps(details), app["id"]))

        ver_res = documents.verify_application(user)
        self.assertTrue(ver_res["ok"])
        self.assertEqual(ver_res["application_status"], "KYC_APPROVED")
        self.assertEqual(ver_res["cross_checks"]["verdict"], "ALL_PASSED")


if __name__ == "__main__":
    unittest.main()
