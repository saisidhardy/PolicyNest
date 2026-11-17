# PolicyNest System Architecture

## 1. Executive Summary

PolicyNest is an enterprise-grade POSP (Point of Sales Person) insurance agent onboarding, verification, training, examination, operations, and certification platform. This document defines the dual-mode architecture:
1. **Interactive Static Showcase**: Hosted on GitHub Pages (`https://saisidhardy.github.io/PolicyNest/`) as an honest, interactive client-side walkthrough using synthetic data personas with zero plaintext credentials stored.
2. **Unified Full Local Application**: Executed via `python server.py` (`http://localhost:8000`), integrating a real SQLite database (`policynest.sqlite3`), Scrypt password hashing, HttpOnly session cookies, server-enforced RBAC/ABAC, private document storage outside web root (`documents_storage/`), local development email inbox (`GET /api/dev/inbox`), deterministic sandbox verification providers (PAN, Aadhaar, Bank, Class 10, Face Match, IRDAI Registry, Malware), real first-party analytics (`POST /api/analytics/events`), and live health probes.

---

## 2. Architecture Comparison: Before vs. After

### Before
- Client-side mock state using `localStorage.getItem('pn_local_users')` storing plaintext passwords.
- Client-side role inference (`email.indexOf('rev') >= 0` inferred reviewer permissions).
- Insecure auto-registration on failed login attempts.
- Regulated verification results returned simulated mock flags without clear sandbox disclosures.
- Documents stored in memory or public browser storage without server validation.
- Zero local email verification loop; users saw network errors (`Failed to fetch`) on static hosting.

### After
- **Single-Command Unified Server**: `python server.py` serves the frontend bundle and `/api/*` endpoints on port 8000.
- **Real SQLite Database**: 37 tables with WAL mode, foreign keys, transaction safety, and 11 versioned migrations.
- **Cryptographic Security**:
  - Scrypt password hashing with unique salts (cost=16384, r=8, p=1).
  - High-entropy cryptographic session tokens (256-bit) stored in server-side session table.
  - HttpOnly, SameSite=Lax session cookies.
  - Per-session anti-CSRF tokens for all state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
- **Server-Enforced Role-Based and Attribute-Based Access Control (RBAC/ABAC)**:
  - Strict server policies (`policy.py`) governing applicant, reviewer, compliance admin, and operations roles.
  - Reviewers cannot access unauthorized cases; applicants can only access their own dossier.
- **Deterministic Sandbox Verification Providers**:
  - PAN, Aadhaar, Bank Penny-Drop, Class 10 Marksheet, Face Match, IRDAI Central Registry, and Malware Scanner.
  - Clearly and honestly labeled as `SANDBOX` or `SIMULATED` with deterministic test trigger values.
- **Local Development Email Outbox**:
  - Outbound emails (verification links, password reset tokens, notifications) are recorded in `communication_dispatches` and accessible via `GET /api/dev/inbox`.
- **First-Party Analytics & Dynamic Dashboard**:
  - `analytics_events` table persists scrubbed client and server telemetry.
  - `GET /api/analytics/dashboard` dynamically computes real funnel metrics, conversion rates, and document failure distributions.
- **Observability & Diagnostics**:
  - Real health probes: `/health` (uptime, process status) and `/ready` (DB connectivity, migrations, filesystem permissions).
  - Subsystem verification probe: `/api/admin/verification` auditing 16 platform subsystems.

---

## 3. Subsystem Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                 CLIENT TIER                                       |
|  - High-Fidelity Responsive HTML5 / CSS3 / Vanilla JS                             |
|  - Dual Mode Detection: Static Showcase (GitHub Pages) vs. Local Mode (server.py) |
|  - Accessible Forms (WCAG 2.1 AA) with English & Hindi Localization               |
|  - In-Browser Web Vitals & Event Telemetry (PII-Scrubbed)                        |
+------------------------------------------+----------------------------------------+
                                           | HTTP / REST (port 8000)
                                           v
+-----------------------------------------------------------------------------------+
|                        UNIFIED SERVER & DISPATCHER (server.py)                    |
|  - HTTP Request Router (main.py / portal.py)                                     |
|  - CORS & Allowed Origins Validation                                              |
|  - Rate Limiting Middleware (IP & Account level)                                 |
|  - Session Cookie & CSRF Token Validation                                         |
+---------------------+-------------------------------+-----------------------------+
                      |                               |
       +--------------v---------------+  +------------v--------------------+
       |   CORE BUSINESS WORKFLOWS    |  |       SECURITY & AUTH ENGINE     |
       |  - Onboarding & Autosave     |  |  - Scrypt / Argon2 Password Hash |
       |  - Document Intake & OCR     |  |  - Session Token Management      |
       |  - Reviewer Queue & Ops      |  |  - Server-Side Policy (policy.py)|
       |  - LMS & Exam Engine         |  |  - Rate Limiter (Token Bucket)  |
       |  - Certification Engine      |  |  - Anti-CSRF Synchronizer Token  |
       |  - Appeals & Fraud Sentinel  |  +----------------------------------+
       +--------------+---------------+
                      |
       +--------------v---------------+  +----------------------------------+
       |   DETERMINISTIC SANDBOX      |  |      FIRST-PARTY TELEMETRY       |
       |   VERIFICATION ADAPTERS      |  |  - Event Ingestion Engine        |
       |  - PAN Holder Lookup         |  |  - Dynamic Funnel Aggregator     |
       |  - Aadhaar Offline XML       |  |  - Web Vitals Ingestion          |
       |  - Bank Penny Drop (NPCI)    |  |  - Structured Error Logging      |
       |  - Face Liveness & Match     |  +----------------------------------+
       |  - IRDAI Central Registry    |
       |  - Malware Scanning Engine   |
       +--------------+---------------+
                      |
       +--------------v-----------------------------------------------------+
       |                         DATA & STORAGE TIER                        |
       |  - SQLite Database (`policynest.sqlite3`) with WAL Mode            |
       |  - 37 Relational Tables & 11 Versioned Migrations                  |
       |  - Private Secure Document Directory (`documents_storage/`)       |
       |  - In-Database Communication Outbox (`communication_dispatches`)   |
       +--------------------------------------------------------------------+
```

---

## 4. Key Component Breakdown

### 4.1 Authentication & Session Management
- **Password Security**: Hashed with standard Python `hashlib.scrypt` using 16-byte cryptographically secure salt (`secrets.token_bytes(16)`), CPU/memory cost parameter $N=16384$, block size $r=8$, parallelization $p=1$.
- **Session Tokens**: 256-bit cryptographically secure strings (`secrets.token_urlsafe(32)`).
- **Session Expiry**: Inactivity timeout after 30 minutes; absolute hard timeout after 24 hours.
- **CSRF Defense**: State-changing operations require matching the double-submitted or header-supplied anti-CSRF token generated upon authentication.

### 4.2 Document Intake & Isolation
- **Storage Location**: Private filesystem directory `documents_storage/` located outside the static web server root.
- **File Validation**: Magic-byte inspection validates file MIME types (PDF, PNG, JPEG) and enforces 10 MB upload limits.
- **Malware Scanner**: File signatures scanned against standard definitions before storage.
- **Access Control**: Documents are referenced via opaque UUIDs; direct filesystem paths are never exposed to clients. Downloading a document requires authenticated applicant ownership or reviewer authorization.

### 4.3 Deterministic Sandbox Provider Adapters
- **PAN Verification**: Simulates NSDL Tax Information Network lookup with deterministic mock scenarios.
- **Aadhaar Verification**: Simulates UIDAI Offline e-KYC XML verification with 4-digit share codes.
- **Bank Account Verification**: Simulates NPCI penny-drop account name resolution.
- **Face Liveness & Match**: Simulates biometric comparison between live selfie and ID photo.
- **IRDAI Central Registry**: Checks whether candidate holds an active appointment with another insurer.

### 4.4 First-Party Telemetry & Analytics
- Ingests Web Vitals (`LCP`, `CLS`, `INP`) and custom business funnel events.
- All incoming payloads are strictly scrubbed of PII (PAN, Aadhaar numbers, passwords, phone numbers) before persistence.
- Aggregations are calculated dynamically from SQLite tables without reliance on external analytics services.
