# PolicyNest Privacy-Safe Product Analytics Event Catalog

**Standard:** Privacy by Design, Zero PII Ingestion, Consent-Gated (`docs/ANALYTICS_PRIVACY.md`)  
**Architecture:** First-Party Event Bus with Client-Side Redaction Filter  

---

## 1. Naming & Structure Conventions

Every analytics event follows the strict schema:
```json
{
  "event_name": "verb_object_qualifier",
  "timestamp": 1731828000,
  "session_id": "sess_8f3a1c",
  "properties": { ... }
}
```

---

## 2. Authorized Event Catalog

### Funnel 1: Public Acquisition & Onboarding
1. `public_landing_viewed`
   - **Trigger:** Public landing page loads.
   - **Allowed Properties:** `language`, `theme`, `referrer_domain`, `screen_width_category`.
   - **Forbidden Properties:** IP address, user identity, exact location.
2. `onboarding_explainer_opened`
   - **Trigger:** User clicks on any of the 8 stations on the interactive journey map.
   - **Allowed Properties:** `stage_name`, `interaction_type` (`click` vs `keyboard`).
3. `account_creation_started`
   - **Trigger:** Registration modal opens.
   - **Allowed Properties:** `source_button` (`hero` vs `header`).
4. `account_creation_completed`
   - **Trigger:** Successful account creation.
   - **Allowed Properties:** `role` (`applicant`).
   - **Forbidden Properties:** Email, name, password hash.
5. `sign_in_succeeded` / `sign_in_failed`
   - **Trigger:** Sign-in authentication result.
   - **Allowed Properties:** `error_code` (if failed: `invalid_credentials` / `locked`).

### Funnel 2: Application Completion
6. `application_started`
   - **Trigger:** Applicant clicks "Start application" or resumes draft.
   - **Allowed Properties:** `application_reference_prefix` (e.g. `PN-2026`).
7. `application_section_completed`
   - **Trigger:** Candidate completes personal basics page.
   - **Allowed Properties:** `section_name` (`basics`), `duration_seconds`.
   - **Forbidden Properties:** Real names, dates of birth, addresses.
8. `application_autosave_succeeded` / `application_autosave_failed`
   - **Trigger:** Autosave completes.
   - **Allowed Properties:** `version_number`, `latency_ms`.

### Funnel 3: Document Uploads & Quality
9. `document_upload_started` / `document_upload_completed`
   - **Trigger:** Document chosen and processed by local WASM OCR.
   - **Allowed Properties:** `slot` (`PAN`, `AADHAAR_FRONT`, `BANK`), `mime_type`, `quality_score_band` (`high`, `medium`, `low`), `ocr_confidence_band`.
   - **Forbidden Properties:** Filename (may contain person's name), extracted OCR text, image payload.
10. `document_replacement_completed`
    - **Trigger:** Applicant re-uploads a corrected document after rework notice.
    - **Allowed Properties:** `slot`, `version`.

### Funnel 4: Verification & Underwriting
11. `verification_started` / `verification_completed`
    - **Trigger:** Subsystem cross-document check finishes.
    - **Allowed Properties:** `check_type`, `outcome` (`PASS`, `HUMAN_REVIEW`, `DEFECT`), `is_simulated`.
12. `reviewer_case_opened`
    - **Trigger:** Staff underwriter inspects dossier.
    - **Allowed Properties:** `queue_type`, `turnaround_hours_band`.
13. `reviewer_changes_requested` / `reviewer_application_approved`
    - **Trigger:** Decision recorded.
    - **Allowed Properties:** `rule_citation` (`§2.1`, `§4.2`), `decision_status`.
    - **Forbidden Properties:** Free-form reviewer notes, applicant details.

### Funnel 5: Training & Examination
14. `training_module_started` / `training_module_completed`
    - **Trigger:** Candidate studies regulatory curriculum.
    - **Allowed Properties:** `module_id` (`MOD-01` to `MOD-05`), `hours_spent_band`.
15. `exam_started` / `exam_submitted`
    - **Trigger:** 50-question assessment launched or finished.
    - **Allowed Properties:** `attempt_number`, `score_band` (`>= 35%`, `< 35%`), `passed` (`true`/`false`).
    - **Forbidden Properties:** Question IDs, specific chosen answers.

### Funnel 6: Certification & Verification
16. `posp_agreement_executed`
    - **Trigger:** Digital appointment agreement e-Signed.
    - **Allowed Properties:** `version` (`2026.1`).
17. `certificate_issued` / `certificate_downloaded`
    - **Trigger:** POSP certificate issued or saved as PDF/SVG.
    - **Allowed Properties:** `lines_of_business` (`Life,General,Health`).
18. `certificate_public_verified`
    - **Trigger:** Public QR or portal verification query executed.
    - **Allowed Properties:** `verified` (`true`/`false`), `status` (`ACTIVE`/`REVOKED`).
