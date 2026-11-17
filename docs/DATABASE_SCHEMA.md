# PolicyNest Database Schema and Migrations

## 1. Overview

PolicyNest uses a local SQLite database (`policynest.sqlite3`) with WAL (Write-Ahead Logging) mode, synchronous pragma `NORMAL`, foreign key constraints enabled, and 11 versioned, reversible migrations.

---

## 2. Migration Version History

| Migration | Identifier | Summary |
|---|---|---|
| `001` | `001_initial_schema` | Core users, sessions, roles, and password reset tokens |
| `002` | `002_cases_and_workflows` | Cases, application drafts, state transitions, reviewer assignments |
| `003` | `003_documents_and_storage` | Document metadata, secure storage paths, MIME types, OCR data |
| `004` | `004_verification_results` | KYC checks, PAN, Aadhaar, Bank verification logs |
| `005` | `005_training_lms` | Training modules, user progress, completion timestamps |
| `006` | `006_examination_engine` | Question bank, exam attempts, proctoring incident logs |
| `007` | `007_certification` | Issued POSP certificates, digital signatures, agreement execution |
| `008` | `008_fraud_and_appeals` | Blacklists, fraud investigation flags, appeal tickets |
| `009` | `009_communications_outbox` | In-app communication dispatches (Email/SMS outbox) |
| `010` | `010_audit_and_compliance` | Immutable audit trail, compliance pack snapshots |
| `011` | `011_email_verification_and_analytics_expansion` | Real email verification tokens, first-party analytics events, health snapshots |

---

## 3. Core Table Definitions

### 3.1 `users`
Primary user identity and credential table.
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'applicant', -- 'applicant', 'reviewer', 'admin', 'ops'
    created_at INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    email_verified INTEGER NOT NULL DEFAULT 0,
    mobile_verified INTEGER NOT NULL DEFAULT 0,
    mobile_masked TEXT,
    analytics_consent INTEGER NOT NULL DEFAULT 0,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_algo TEXT NOT NULL DEFAULT 'scrypt',
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
```

### 3.2 `sessions`
Server-side high-entropy session storage.
```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_active INTEGER NOT NULL,
    ip_hash TEXT,
    user_agent TEXT,
    csrf_token TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
```

### 3.3 `email_verification_tokens`
Tokens for the local email verification loop.
```sql
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_evt_user ON email_verification_tokens(user_id);
```

### 3.4 `cases`
The central POSP application lifecycle table.
```sql
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, -- e.g. 'PN-2026-XXXX'
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL, -- State machine status
    reviewer_id INTEGER REFERENCES users(id),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    submitted_at INTEGER,
    decided_at INTEGER,
    readiness_score REAL DEFAULT 0.0,
    sla_deadline INTEGER,
    priority TEXT DEFAULT 'NORMAL'
);
CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_reviewer ON cases(reviewer_id);
```

### 3.5 `documents`
Metadata and physical storage pointer for uploaded candidate files.
```sql
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, -- UUID
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    document_type TEXT NOT NULL, -- 'PAN', 'AADHAAR_FRONT', 'AADHAAR_BACK', 'CHEQUE', 'MARKSHEET', 'PHOTO'
    file_path TEXT NOT NULL, -- Path inside documents_storage/
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    ocr_raw_text TEXT,
    ocr_extracted_data JSON,
    verification_status TEXT DEFAULT 'PENDING',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_case ON documents(case_id);
```

### 3.6 `communication_dispatches`
In-database local email and SMS outbox.
```sql
CREATE TABLE IF NOT EXISTS communication_dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    channel TEXT NOT NULL, -- 'EMAIL', 'SMS', 'IN_APP'
    template_key TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT,
    content TEXT NOT NULL,
    body_preview TEXT,
    status TEXT NOT NULL DEFAULT 'DELIVERED',
    metadata_json TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comm_user ON communication_dispatches(user_id);
CREATE INDEX IF NOT EXISTS idx_comm_recipient ON communication_dispatches(recipient);
```

### 3.7 `analytics_events`
First-party event telemetry table with scrubbed PII.
```sql
CREATE TABLE IF NOT EXISTS analytics_events (
    event_id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_id TEXT,
    event_name TEXT NOT NULL,
    event_category TEXT NOT NULL,
    properties_json TEXT,
    url TEXT,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analytics_event_name ON analytics_events(event_name);
CREATE INDEX IF NOT EXISTS idx_analytics_ts ON analytics_events(timestamp);
```

### 3.8 `audit_events`
Append-only tamper-evident compliance audit trail.
```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    ip_address TEXT,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_events(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_id);
```
