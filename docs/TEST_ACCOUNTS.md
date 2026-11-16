# PolicyNest QA Test Accounts & Synthetic Case Catalog

The following synthetic test accounts and case fixtures are automatically provisioned by the **Seed QA Scenarios** feature (`POST /api/qa/seed` or the Verification Dashboard `#verification`).

> **Note on Security:**  
> These credentials and accounts exist strictly in **Non-Production** environments (`IS_PRODUCTION=False`). In production builds, synthetic accounts and the seed/reset endpoints are strictly disabled and blocked by ABAC policy guards.

---

## 1. Staff Test Accounts

| Role | Email | Password | Department | Access Level |
|---|---|---|---|---|
| **Underwriting Reviewer** | `rev.ops@policynest.test` | `ReviewerPass2026!` | Operations | Claims cases, reviews documents, issues KYC decisions (§2.1, §4.2) |
| **Senior Reviewer** | `senior.rev@policynest.test` | `SeniorPass2026!` | Underwriting | Handles escalations and applicant appeals |
| **Compliance Officer** | `compliance@policynest.test` | `CompliancePass2026!` | Legal & Compliance | Full audit trail inspection, regulatory pack export |
| **Fraud Investigator** | `fraud.desk@policynest.test` | `FraudDesk2026!` | Risk & Fraud Desk | Investigates restricted fraud hold tickets and rings |
| **System Administrator** | `admin.ops@policynest.test` | `AdminPass2026!` | Technology | Provisions staff accounts and inspects subsystem health |

---

## 2. Canonical Verification Cases (11 Scenarios Across 13 States)

| Case Reference | Applicant Name | Email | State | Purpose & Verification Flow |
|---|---|---|---|---|
| `PN-2026-SYN01` | Priya Sharma | `priya.sharma@policynest.test` | `DRAFT` | Verifies draft autosave and incomplete state handling |
| `PN-2026-SYN02` | Rajesh Kumar | `rajesh.kumar@policynest.test` | `SUBMITTED` | In the unassigned review queue; ready to be claimed by a reviewer |
| `PN-2026-SYN03` | Sunita Patel | `sunita.patel@policynest.test` | `NEEDS_MORE_INFO` | Verifies constructive applicant rework notification for blurry PAN |
| `PN-2026-SYN04` | Vikram Malhotra | `vikram.malhotra@policynest.test` | `KYC_APPROVED` | KYC verified; applicant is unlocked and actively in Training (15h) |
| `PN-2026-SYN05` | Ananya Desai | `ananya.desai@policynest.test` | `TRAINING_COMPLETE` | All 5 modules completed; candidate is eligible to launch the exam |
| `PN-2026-SYN06` | Deepa Nair | `deepa.nair@policynest.test` | `EXAM_FAILED` | Verifies 24-hour retake cooldown timer display |
| `PN-2026-SYN07` | Amit Verma | `amit.verma@policynest.test` | `EXAM_PASSED` | Exam passed; candidate is ready to sign the POSP Appointment Agreement |
| `PN-2026-SYN08` | Pooja Gupta | `pooja.gupta@policynest.test` | `AGREEMENT_EXECUTED`| Agreement executed; pending certificate issuance |
| `PN-2026-SYN09` | Suresh Menon | `suresh.menon@policynest.test` | `CERTIFIED` | Active POSP Certificate `PN-POSP-2026-00001` with valid HMAC signature |
| `PN-2026-SYN10` | Rahul Joshi | `rahul.joshi@policynest.test` | `FRAUD_HOLD` | Demonstrates the Anti-Accusation Invariant (neutral message to applicant) |
| `PN-2026-SYN11` | Kavita Reddy | `kavita.reddy@policynest.test` | `APPEAL_PENDING` | Active appeal under review by Senior Reviewer |

---

## 3. How to Reset Test Data

To safely purge all synthetic test cases and restore a clean database without modifying production user accounts:
- In the UI: Navigate to `#verification` and click **"Reset Test Data"**.
- Via API: `POST /api/qa/reset` (requires admin authorization or non-production environment).
- Purge Target: Purges records matching `@policynest.test` and `PN-%-SYN%`. Real customer accounts are strictly preserved.
