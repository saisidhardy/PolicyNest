# PolicyNest End-to-End Demonstration Guide

This guide details how to demonstrate the complete, production-grade POSP onboarding journey locally without external dependencies or recurring subscription fees.

---

## 1. Persona Overview

| Persona | Name | Role | Email | Password | Starting State |
|---|---|---|---|---|---|
| 1 | **Aarav Patel** | Applicant | `aarav.patel@example.com` | `Password1234!` | Profile created, no documents uploaded |
| 2 | **Priya Sharma** | Applicant | `priya.sharma@example.com` | `Password1234!` | Documents submitted, awaiting KYC & review |
| 3 | **Vikram Malhotra** | Reviewer | `reviewer@policynest.in` | `ReviewerPass123!` | Active reviewer cockpit with assigned queue |
| 4 | **Compliance Admin** | Administrator | `admin@policynest.in` | `AdminMaster123!` | System verification, analytics & audit controls |

---

## 2. Step-by-Step Demonstration Flow

```
+-----------------------------------------------------------------------------------------+
|                                    DEMO FLOW SUMMARY                                    |
|                                                                                         |
|  [Step 1: Registration]                                                                 |
|         |                                                                               |
|         v                                                                               |
|  [Step 2: Local Email Verification via /api/dev/inbox]                                  |
|         |                                                                               |
|         v                                                                               |
|  [Step 3: Document Uploads & Private Storage]                                           |
|         |                                                                               |
|         v                                                                               |
|  [Step 4: Deterministic Sandbox KYC & Cross-Checks]                                     |
|         |                                                                               |
|         v                                                                               |
|  [Step 5: Reviewer Queue & Correction Workflow]                                         |
|         |                                                                               |
|         v                                                                               |
|  [Step 6: Accelerated 15-Hour LMS Training & Proctored Exam]                            |
|         |                                                                               |
|         v                                                                               |
|  [Step 7: POSP Certification Issuance & Public Verification]                            |
|         |                                                                               |
|         v                                                                               |
|  [Step 8: First-Party Analytics Dashboard & Immutable Audit Trail]                      |
+-----------------------------------------------------------------------------------------+
```

### Step 1: Real Local Registration
1. Navigate to `http://localhost:8000/`.
2. Click **Create account**.
3. Enter Name (`Ananya Verma`), Email (`ananya.verma@example.com`), and Password (12+ characters, e.g., `SecurePass1234!`).
4. Submit the form:
   - The backend creates an account in `policynest.sqlite3` with Scrypt password hashing.
   - An email verification dispatch is logged into `communication_dispatches`.
   - The UI displays an alert: *"Verification email sent. Check your inbox to verify your account."*

### Step 2: Local Mail Inbox Inspection
1. Open a new tab to `http://localhost:8000/api/dev/inbox?recipient=ananya.verma@example.com` (or view via the Developer Tools Drawer).
2. Inspect the latest record:
   - `subject`: "Verify your PolicyNest Account"
   - `metadata`: Contains verification token and link `http://localhost:8000/api/auth/verify-email?token=...`
3. Click or execute the verification request to activate the account.

### Step 3: Profile Completion & Document Upload
1. Log in with the verified credentials.
2. Complete Step 1: Personal Details (Date of Birth, Gender, Address, Mobile).
3. Complete Step 2: Document Uploads. Upload synthetic specimen documents:
   - PAN Card Specimen (`specimen_pan.png`)
   - Aadhaar Front/Back (`specimen_aadhaar.png`)
   - Cancelled Cheque / Bank Statement (`specimen_cheque.png`)
   - Class 10 Certificate (`specimen_marksheet.png`)
   - Passport Photograph / Selfie (`specimen_photo.png`)
4. Verify:
   - Files are stored in `documents_storage/` outside the web root.
   - Files are scanned for malware signatures by `MalwareScannerProvider`.
   - OCR extracts document numbers and applicant names.

### Step 4: Sandbox KYC & Cross-Checks
1. Click **Run Verification Checks**.
2. Deterministic Sandbox Adapters execute:
   - **PAN Holder Verification**: Confirms name match and active PAN status.
   - **Aadhaar e-KYC**: Validates 4-digit share code and offline XML.
   - **Bank Penny Drop**: Validates IFSC and account holder name match.
   - **Facial Comparison**: Computes similarity index (0.94) and liveness score (0.98).
   - **IRDAI Central Registry**: Confirms zero conflicting agency appointments.
3. Observe that all verification badges are clearly and honestly labeled **"Simulated"** or **"Sandbox"**.

### Step 5: Reviewer Queue & Rework Flow
1. Sign out and sign in as Reviewer (`reviewer@policynest.in` / `ReviewerPass123!`).
2. Open the **Reviewer Cockpit** (`/api/reviewer/queue`).
3. Select Ananya Verma's case.
4. Issue a Correction Request:
   - Mark Class 10 certificate: *"Document image is blurry. Please re-upload a clear copy."*
   - Submit decision. The state transitions to `CORRECTION_REQUESTED`.
5. Sign in as Ananya Verma:
   - The dashboard updates with a clear banner: *"Action Required: Please replace your Class 10 Certificate."*
   - Re-upload clear specimen. Submit correction.
   - Case returns to reviewer queue as `RESUBMITTED`.
6. Reviewer approves all documents: State advances to `VERIFIED_PENDING_TRAINING`.

### Step 6: 15-Hour Accelerated Training LMS & Proctored Exam
1. As applicant, navigate to **POSP Training LMS**.
2. Complete the 5 mandated modules (Life Insurance, General Insurance, Health Insurance, POSP Code of Conduct, AML/KYC).
3. In demo mode, select **Accelerate Demo Timer** to fast-track module completion.
4. Unlock proctored examination:
   - 20 multiple-choice questions dynamically drawn from the IRDAI syllabus question bank.
   - Answer 15+ correctly (75%+ pass threshold).
   - Submit exam. Server evaluates answers and issues immediate PASS result.

### Step 7: POSP Certification Issuance & Public Verification
1. Review and digitally execute the POSP Service Agreement (OTP confirmation).
2. The platform generates an official POSP Certificate:
   - Unique Certificate Identifier: `PN-POSP-2026-XXXXXX`
   - Signed QR Code and public verification URL: `http://localhost:8000/api/certificates/verify/PN-POSP-2026-XXXXXX`
3. Open the public URL in an incognito window without authentication:
   - Confirms valid certificate status, candidate name, IRDAI line of business, and issue timestamp.
   - Clearly states: *"Demo / Sandbox Certificate for Operational Testing"*.

### Step 8: Dynamic Analytics & Audit Trail
1. Sign in as Administrator (`admin@policynest.in` / `AdminMaster123!`).
2. Open the **Analytics Dashboard** (`/api/analytics/dashboard`):
   - View dynamically computed conversion rates across the 7 onboarding milestones.
   - Inspect document error drop-off rates and average reviewer turnaround times.
3. Open the **Immutable Audit Log** (`/api/audit/timeline`):
   - Every state transition, login, upload, reviewer decision, and exam completion is logged with timestamp, actor ID, and IP address.
