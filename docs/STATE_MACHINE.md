# PolicyNest POSP Application State Machine

## 1. State Machine Overview

The POSP onboarding lifecycle is governed by an explicit server-side state machine. All transitions are validated by `status_model.py` and authorized by `policy.py`. Client applications cannot arbitrarily modify state.

---

## 2. Finite States Catalog

| State Key | Display Name | Owner Persona | Description |
|---|---|---|---|
| `DRAFT` | Draft Application | Applicant | Profile form in progress; autosaving enabled |
| `DOCUMENTS_PENDING` | Documents Pending | Applicant | Profile saved; documents being uploaded |
| `VERIFICATION_IN_PROGRESS` | Verification Running | System / Automated | Sandbox verification adapters evaluating inputs |
| `SUBMITTED` | Submitted for Review | Reviewer Pool | Application locked from editing; in reviewer queue |
| `UNDER_REVIEW` | Under Human Review | Assigned Reviewer | Active review by senior operations specialist |
| `CORRECTION_REQUESTED` | Rework Required | Applicant | Reviewer requested corrections on specific documents |
| `RESUBMITTED` | Resubmitted | Assigned Reviewer | Applicant fixed flagged items; back in review queue |
| `VERIFIED_PENDING_TRAINING` | Documents Approved | Applicant | KYC approved; 15-hour LMS training unlocked |
| `TRAINING_IN_PROGRESS` | Training LMS Active | Applicant | Completing mandatory training modules |
| `TRAINING_COMPLETED` | Training Completed | Applicant | All 5 modules completed; exam unlocked |
| `EXAMINATION_IN_PROGRESS` | Exam Active | Applicant | 20-question proctored IRDAI syllabus exam |
| `EXAMINATION_FAILED` | Exam Retake Required | Applicant | Score below 75%; 24h cooldown (overridable by admin) |
| `EXAMINATION_PASSED` | Exam Passed | Applicant | Score >= 75%; POSP agreement ready for sign-off |
| `AGREEMENT_EXECUTED` | Agreement Signed | System | POSP Code of Conduct digitally confirmed via OTP |
| `CERTIFIED` | Certified POSP Agent | All | Official digital certificate issued; active agent |
| `REJECTED` | Application Rejected | Applicant / Reviewer | Permanent rejection (fraud, eligibility, duplicate) |
| `APPEAL_SUBMITTED` | Appeal Under Review | Compliance Admin | Applicant submitted appeal against rejection |

---

## 3. Transition Matrix

```
  +--------------+
  |    DRAFT     |
  +-------+------+
          | (Applicant completes personal info)
          v
  +-----------------------+
  |   DOCUMENTS_PENDING   |
  +-------+---------------+
          | (All mandatory documents uploaded)
          v
  +-------------------------------+
  |   VERIFICATION_IN_PROGRESS    |
  +-------+-----------------------+
          | (Sandbox KYC adapters return PASS)
          v
  +---------------+
  |   SUBMITTED   |
  +-------+-------+
          | (Reviewer claims case)
          v
  +------------------+     (Reviewer flags flaw)      +------------------------+
  |   UNDER_REVIEW   +------------------------------->+  CORRECTION_REQUESTED  |
  +-------+----------+                                +-----------+------------+
          |                                                       |
          | (Reviewer Approves)                                   | (Applicant re-uploads)
          |                                                       v
          |                                           +------------------------+
          +-------------------------------------------+      RESUBMITTED       |
          |
          v
  +-------------------------------+
  |   VERIFIED_PENDING_TRAINING   |
  +-------+-----------------------+
          | (Applicant starts module 1)
          v
  +-------------------------------+
  |     TRAINING_IN_PROGRESS      |
  +-------+-----------------------+
          | (All 5 LMS modules completed)
          v
  +-------------------------------+
  |      TRAINING_COMPLETED       |
  +-------+-----------------------+
          | (Applicant launches exam)
          v
  +-------------------------------+     (Score < 75%)     +--------------------+
  |    EXAMINATION_IN_PROGRESS    +---------------------->+ EXAMINATION_FAILED |
  +-------+-----------------------+                       +---------+----------+
          |                                                         |
          | (Score >= 75%)                                          | (Cooldown / Retake)
          v                                                         +--------+
  +-------------------------------+
  |      EXAMINATION_PASSED       |
  +-------+-----------------------+
          | (Applicant signs POSP Agreement via OTP)
          v
  +-------------------------------+
  |      AGREEMENT_EXECUTED       |
  +-------+-----------------------+
          | (Digital Certificate minted)
          v
  +-------------------------------+
  |           CERTIFIED           |
  +-------------------------------+
```

---

## 4. State Security & RBAC Invariants

1. **No Skip-Ahead**: An applicant cannot enter `EXAMINATION_IN_PROGRESS` without `TRAINING_COMPLETED`.
2. **Immutable Submitted State**: When a case is `SUBMITTED` or `UNDER_REVIEW`, applicant edits to personal data and documents are strictly rejected with HTTP 403 Forbidden.
3. **Reviewer Decision Atomicity**: Every transition to `CORRECTION_REQUESTED`, `VERIFIED_PENDING_TRAINING`, or `REJECTED` writes an atomic record to `reviewer_decisions` and `audit_events`.
4. **Appeals Isolation**: Only rejected cases (`REJECTED`) can file an appeal (`POST /api/appeals`). Only administrators can resolve an appeal (`POST /api/appeals/decide`).
