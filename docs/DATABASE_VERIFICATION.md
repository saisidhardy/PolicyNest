# PolicyNest Database Architecture & Persistence Verification

**Database Engine:** SQLite 3 with Write-Ahead Logging (WAL) Mode  
**Concurrency Protocol:** Optimistic Version Locking (`version = version + 1`)  
**Foreign Keys:** Enforced via `PRAGMA foreign_keys = ON`  

---

## 1. Schema & Migration Architecture

PolicyNest manages schema evolution through 10 sequential, forward-only migrations (`copilot_api/migrations.py`):
1. **Migration 1 (`001_initial_schema`):** Core `users`, `applications`, `cases`, `sessions`, `timeline`, and `notifications` tables.
2. **Migration 2 (`002_verification_tables`):** `verification_results`, `cross_document_checks`, and `external_provider_logs`.
3. **Migration 3 (`003_document_records`):** Content-addressable `document_records` with quality scores and slot defect tracking.
4. **Migration 4 (`004_underwriting_operations`):** `review_notes`, SLA tracking, cooling-off dates, and `appeals`.
5. **Migration 5 (`005_fraud_engine`):** `fraud_cases`, device fingerprint hashes, and blacklist registries.
6. **Migration 6 (`006_training_lms`):** `training_modules` curriculum and `training_progress` with anti-tamper heartbeat stamps.
7. **Migration 7 (`007_examination_engine`):** `exam_question_bank` (50 randomized questions) and `exam_attempts`.
8. **Migration 8 (`008_certification_authority`):** `certificates` with HMAC-SHA256 digests and `posp_agreements`.
9. **Migration 9 (`009_notifications_outbox`):** `communication_dispatches` for multi-channel email/SMS logs.
10. **Migration 10 (`010_verification_audit`):** Subsystem health log and automated seed tracking.

---

## 2. Concurrency & Optimistic Version Locking

To prevent race conditions during concurrent auto-saves across multiple browser tabs:
- The `applications` table maintains an integer `version` column.
- On each save request (`application.save_draft`), the client passes its known version.
- The server executes:
  ```sql
  UPDATE applications
  SET version = ?, details = ?, progress = ?, updated_at = ?
  WHERE user_id = ? AND version = ?
  ```
- If another tab updated the record first, the affected rows count is 0, raising a clean `conflict_detected` error, prompting the client to refresh its state without corrupting data.

---

## 3. Database Resilience & Backup Strategy

1. **WAL Mode Performance:**
   - Readers never block writers, and writers never block readers.
   - Commit latency is reduced to sub-millisecond speeds.
2. **Online Hot Backups:**
   - Execute live snapshots using SQLite's `VACUUM INTO`:
     ```bash
     sqlite3 policynest.db "VACUUM INTO 'backups/policynest_hot_backup.db';"
     ```
3. **Integrity Validation:**
   - Pre-flight deployment check runs `PRAGMA integrity_check;` ensuring zero database corruption.
