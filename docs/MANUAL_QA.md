# PolicyNest Manual QA & Verification Script

This document details the exact step-by-step manual test scenarios for testing and verifying the PolicyNest onboarding and operations platform across all user roles.

---

## Pre-requisites & Verification Entry Point

1. Navigate to the deployed instance:
   - **GitHub Pages:** `https://saisidhardy.github.io/PolicyNest/`
   - **Local Host:** `http://localhost:8000/`
2. Access the **System Verification Dashboard** via the footer link **"System Verification & QA"** or direct hash `#verification`:
   - Verify that the Environment Badge displays `LOCAL`, `TEST`, or `PROD`.
   - Verify that all 16 platform subsystems display their live status.
   - Click **"Seed 11 QA Cases"** to immediately populate the system with pre-configured test accounts across all 13 application states.

---

## Journey 1: End-to-End Applicant Journey (20 Steps)

| Step | Action | Expected Result |
|:---:|---|---|
| **1** | On the landing page, click **"Create your account"**. Enter full name, email, and 12+ character password. Check "Save progress". | Account is created instantly. Success confirmation appears. |
| **2** | Confirm user is redirected to the Applicant Dashboard with active status. | Header shows applicant name, initials, and application reference `PN-2026-XXXXX`. |
| **3** | Click **"Sign out"** and re-login using the credentials. | Successful sign-in without error; session restored. |
| **4** | On Dashboard, click **"Continue application"**. Complete Step 1 (Personal Details: Name, DOB, State, City, Education). | Autosave indicator shows "Saved just now". Version increments. |
| **5** | Close browser tab or refresh the page. | Application resumes exactly at the saved point with all form data intact. |
| **6** | Proceed to Step 2 (Documents). Upload JPEG/PNG images for **PAN**, **Aadhaar Front**, **Aadhaar Back**, **Class 10**, and **Bank Proof**. | Document inspection runs locally. Quality score appears (e.g. 92/100). |
| **7** | (Simulated Rework): Reviewer rejects PAN card as blurry. | Applicant sees notification: *"PAN card needs a clearer photo"*. Status moves to `NEEDS_MORE_INFO`. |
| **8** | Re-upload a crisp photo of the PAN card. | Version increments to 2. Defect marker clears. |
| **9** | Submit application for underwriting review. | Status transitions to `SUBMITTED`. Application locks against applicant modification. |
| **10** | Reviewer requests changes with citation §4.2. | Applicant receives constructive notification in notification inbox with clear fix instructions. |
| **11** | Address the requested change and click **"Resubmit"**. | Status returns to `SUBMITTED`. Reviewer queue shows case in Rework. |
| **12** | Reviewer approves KYC. | Status transitions to `KYC_APPROVED`. Training modules are unlocked. |
| **13** | Open Training section. Study all 5 modules (15 hours curriculum). | Heartbeats record viewing time. Sequential unlocking enforces completed prerequisites. |
| **14** | Complete all 5 modules. Click **"Start Certification Exam"**. | 50 randomized IRDAI questions load. Timer starts. |
| **15** | Answer questions and submit exam. | Instant grading displays. If score >= 35%, status transitions to `EXAM_PASSED`. |
| **16** | Review the POSP Appointment Agreement. Check statutory declaration. Sign digitally. | Agreement is stamped with cryptographic hash. Status transitions to `AGREEMENT_EXECUTED`. |
| **17** | Certificate is issued automatically. | Official Certificate displays with Certificate Number `PN-POSP-2026-XXXXX`. |
| **18** | Click **"Print or save as PDF"** / View SVG. | Clean, tamper-evident digital certificate renders with IRDAI Direct Broker seal. |
| **19** | Copy Certificate Number and verify at `/api/certificates/verify/<number>`. | Zero-auth public verification confirms authentic signature digest. |
| **20** | Open Profile & History tab. | Unified chronological audit timeline lists every registration, upload, review, and exam event. |

---

## Journey 2: Reviewer Operations Lifecycle (12 Steps)

| Step | Action | Expected Result |
|:---:|---|---|
| **1** | Log in with staff credentials (e.g., `rev.ops@policynest.test` / `ReviewerPass2026!`). | Staff banner appears. Review Console displays in main navigation. |
| **2** | Navigate to `#review`. | Reviewer Operations Cockpit loads with queue selector tabs. |
| **3** | Click **"My Queue"**, **"Unassigned Pool"**, and **"Rework Needed"**. | Queue counts and filtered candidate cases display with SLA age chips. |
| **4** | On an unassigned case, click **"Claim"**. | Case moves to "My Queue" and is locked to current reviewer. |
| **5** | Click **"Inspect Dossier"** on the claimed case. | Full Case Dossier opens: Personal details, 5 document slots with quality scores, and cross-checks. |
| **6** | Verify 8-Tier Name Match comparison. | Shows match tier (e.g. Tier 1 Exact Match or Tier 3 Phonetic Match). |
| **7** | Select Decision: **"Request Changes (§4.2)"**. Check defective slot **"BANK"**. Enter note: *"Account number truncated"*. | Decision is recorded. Audit event logs action. Applicant receives constructive notification. |
| **8** | Verify applicant case reflects `NEEDS_MORE_INFO` and moves to Rework queue. | Queue counts update automatically. |
| **9** | Once applicant resubmits, open dossier again. | Shows updated document version and resubmission timestamp. |
| **10** | Select Decision: **"Approve KYC (§2.1)"**. Enter note: *"All documents verified and compliant"*. | Application transitions to `KYC_APPROVED`. Training unlocks for applicant. |
| **11** | Open Timeline / Audit Log for the case. | Every reviewer claim, note, rule citation, and decision is recorded with timestamps. |
| **12** | Click **"Export Regulatory Audit Pack"** (Admin). | Complete JSON compliance pack downloads with SHA-256 integrity digest. |

---

## Journey 3: Account Recovery & Session Revocation (7 Steps)

1. Navigate to `#welcome` and click **"Forgot your password?"**.
2. Enter an existing email: `applicant@policynest.test` -> Identical success message displayed.
3. Enter a non-existent email: `random_user@gmail.com` -> Identical success message displayed (Zero Email Enumeration).
4. Use the issued password reset token to submit a new strong password.
5. Attempt to use the same reset token again -> Token is rejected as single-use / invalidated.
6. Attempt to authenticate using the old password -> Rejected with 401 Unauthorized.
7. Authenticate using the new password -> Successfully signs in; prior session cookies are invalidated.

---

## Journey 4: Cross-Account & Cross-Role Authorization Boundaries (7 Steps)

1. Sign in as Applicant A (`app_a@policynest.test`).
2. Attempt to fetch Applicant B's application via direct API call `/api/applications/2` -> Rejected with 403 Forbidden (IDOR Guard).
3. Attempt to call staff endpoints `/api/reviewer/queues` as Applicant A -> Rejected with 403 Forbidden.
4. Sign in as Reviewer (`reviewer@policynest.test`).
5. Attempt to reset an applicant's password via staff API -> Rejected (Privilege Separation).
6. Set reviewer account status to `suspended` in database or admin panel.
7. Attempt any underwriting decision as the suspended reviewer -> Instantly rejected with 403 Forbidden.
