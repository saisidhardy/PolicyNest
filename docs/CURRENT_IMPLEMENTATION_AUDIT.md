# PolicyNest Current Implementation Audit & Risk Classification

**Author**: Principal Application Security Engineer, Frontend Architect, and DevOps Lead  
**Audit Date**: November 17, 2026  
**Status**: Comprehensive Baseline Completed — Insecure Fallback Remediation Plan Active

---

## 1. Executive Summary

This document performs an exhaustive, transparent security and architectural audit of the PolicyNest codebase across both its **Python Backend (`policynest_mvp/copilot_api`)** and its **Web Frontend (`policynest_mvp/PolicyNest.html` & `index.html`)**.

### Critical Architectural Finding
The PolicyNest codebase actually contains two distinct execution layers:
1. **A Real Production-Shaped Python Backend** (`server.py` and `policynest_mvp/copilot_api/`):
   - Implements a 37-table SQLite database (`policynest.sqlite3`) with WAL journal mode.
   - Secure Scrypt password hashing (`hashlib.scrypt(..., n=2**14, r=8, p=1)`).
   - Server-side HttpOnly cookie sessions, CSRF token verification, and RBAC policies.
   - Complete state machine, document storage outside web root, OCR extraction, training LMS, exam engine, reviewer operations, fraud engines, audit logging, and telemetry ingestion.
   - **215 automated backend tests** currently passing.
2. **An Insecure Browser-Local Fallback** (`localAccountFallback` in `PolicyNest.html`):
   - Injected historically to allow the static GitHub Pages deployment to function without a running backend server.
   - **Critical Vulnerability**: Stores user accounts in `localStorage.setItem('pn_local_users')` with **plaintext passwords** (`password: body.password`).
   - **Critical Vulnerability**: Auto-verifies emails (`email_verified: true`) without sending or verifying confirmation tokens.
   - **Critical Vulnerability**: Grants Reviewer role if the submitted email address contains the substring `"rev"`.
   - **Critical Vulnerability**: Automatically provisions unknown applicant credentials into a new account upon failed login.
   - **Deceptive Claims**: Surfaces hardcoded analytics, static reviewer queues, and hardcoded subsystem verifications.

This audit establishes the mandatory separation: **GitHub Pages becomes an honest Static UI Showcase (prohibiting credential entry and using pre-configured synthetic personas)**, while the **Full Application runs against the real local backend (`python server.py`)**.

---

## 2. Insecure Fallback Audit & Inventory

The following security violations were identified in `policynest_mvp/PolicyNest.html` lines 4130 to 4538:

| Artifact / Pattern | Found In | Description & Vulnerability | Remediation Action |
|:---|:---|:---|:---|
| `pn_local_users` | `PolicyNest.html:4140` | Serializes an array of user objects directly into browser `localStorage`. | **Permanently eliminate**. In local mode, accounts exist only in SQLite `users`. In static showcase, use read-only synthetic fixtures. |
| `pn_current_user` | `PolicyNest.html:4144` | Stores the active authenticated session object in `localStorage`, vulnerable to XSS tampering. | **Permanently eliminate**. Authentication must rely exclusively on server-issued HttpOnly session cookies. |
| `password: body.password` | `PolicyNest.html:4165` | Plaintext user passwords written directly into `localStorage`. | **Immediate deletion**. Passwords must never touch browser client storage. Server hashes with Scrypt. |
| `email.indexOf('rev') >= 0` | `PolicyNest.html:4171` | Grants `reviewer` role if applicant types an email containing "rev". | **Permanently eliminate**. Reviewer roles are strictly provisioned by Admin in SQLite `users` table. |
| Unknown login auto-registration | `PolicyNest.html:4177` | Failed login attempt with length >= 12 silently creates a new account. | **Permanently eliminate**. Failed logins must return HTTP 401 `invalid_credentials`. |
| `email_verified: true` | `PolicyNest.html:4161` | New registrations automatically marked as email-verified. | **Permanently eliminate**. Requires token verification via local dev inbox (`GET /api/dev/inbox`). |
| Hardcoded reviewer cases | `PolicyNest.html:4420-4490` | Static JS object mocks underwriting queue (`PN-2026-00101`). | **Replace with real API**. Reviewer queues query SQLite `cases` and `applications` tables. |
| Hardcoded analytics metrics | `PolicyNest.html:4700-4750` | Static JavaScript numbers displayed as real telemetry. | **Replace with dynamic query**. Calculated from SQLite `business_events` and `technical`. |
| Static subsystem verification | `PolicyNest.html:4800` | Displays "Verified" based on client-side JS flags. | **Replace with live health probe**. Driven by `GET /api/admin/verification`. |

---

## 3. Comprehensive Capability Classification Matrix

| Capability | Current Behavior | Security / Integrity Risk | Can Implement Locally? | Needs External Provider? | Required Action |
|:---|:---|:---|:---:|:---:|:---|
| **Applicant Registration** | Real in API; insecure mock in static fallback | High on static host (plaintext storage) | **Yes** | No | Remove static fallback; point to real API with Scrypt hashing. |
| **Email Verification** | Hardcoded `true` in fallback; token in API | High (unverified email identity) | **Yes** | No (Local Dev Inbox) | Route verification token to local development inbox; require click. |
| **Password Hashing** | Real Scrypt in backend; Plaintext in fallback | Critical (plaintext password exposure) | **Yes** | No | Purge plaintext storage; enforce Scrypt server-side exclusively. |
| **Session Management** | Real HttpOnly session in API; `localStorage` fallback | High (XSS session hijacking) | **Yes** | No | Enforce HttpOnly `SameSite=Lax` server session cookies exclusively. |
| **Role-Based Authorization** | Real ABAC in backend; Email string hack in fallback | Critical (privilege escalation) | **Yes** | No | Enforce server-side role check; restrict reviewer creation to Admin. |
| **Application Persistence** | Real SQLite table in API; `localStorage` fallback | Moderate (data loss on browser clear) | **Yes** | No | Persist in SQLite `applications` table with autosave. |
| **Document Storage** | Real filesystem in backend; base64 in fallback | High (browser memory exhaustion) | **Yes** | No | Store in `documents_storage/` outside web root with MIME validation. |
| **Document OCR** | On-device Tesseract.js WASM | Low (Runs client-side without upload) | **Yes** | No | Retain on-device WASM OCR; test network isolation. |
| **PAN Verification** | Deterministic sandbox adapter in API; mock in fallback | High if claimed as live NSDL | **Yes** (Sandbox) | Yes (for live NSDL) | Label clearly as "Simulated NSDL Sandbox". |
| **Aadhaar Verification** | Verhoeff checksum algorithm + Digilocker mock | High if claimed as live UIDAI | **Yes** (Sandbox) | Yes (for live UIDAI) | Retain Verhoeff algorithm; label as "UIDAI Sandbox". |
| **Bank Penny Drop** | Deterministic IMPS adapter in API | High if claimed as live NPCI | **Yes** (Sandbox) | Yes (for live NPCI) | Label as "NPCI Sandbox"; test ₹1.00 credit simulation. |
| **LMS Training Syllabus** | SQLite `training_progress`; accelerated in demo | Low | **Yes** | No | Persist module hours in SQLite; label demo time acceleration. |
| **Exam Engine** | SQLite `exam_attempts` & synthetic question bank | Low | **Yes** | No | Server-side question randomization and scoring. |
| **Certificate Issuance** | Server-signed SHA-256 HMAC + PDF generator | High if claimed as real IRDAI | **Yes** | No | Prominently stamp: "DEMO CERTIFICATE — NOT A REAL IRDAI CREDENTIAL". |
| **Reviewer Operations** | SQLite `cases` table in API; static array in fallback | High (unauthorized adjudication) | **Yes** | No | Query SQLite directly; require reviewer session authentication. |
| **Appeals & Disputes** | SQLite `appeals` table in API; mock in fallback | Low | **Yes** | No | Persist appeals in SQLite; link to reviewer queue. |
| **Audit Logging** | Append-only SQLite `audit_events` | Critical if absent | **Yes** | No | Persist all security, review, and status transitions in SQLite. |
| **Product Analytics** | SQLite `business_events` in API; hardcoded in fallback | High (deceptive metrics) | **Yes** | No | Ingest via `POST /api/analytics/events`; query dynamically. |
| **Observability & Logs** | Structured JSON logs in API; static in fallback | Moderate | **Yes** | No | Implement live `/health` and `/ready` endpoints. |
| **Production Hosting** | Not present | N/A | No | **Yes** | Document in `docs/PRODUCTION_GAPS.md`. |

---

## 4. Remediation Plan

1. **Purge Browser-Local Insecure Storage**:
   - Strip `pn_local_users`, `pn_current_user`, and plaintext password caching from `PolicyNest.html`.
2. **Implement Dual-Mode Frontend Architecture**:
   - **When Backend is Running (`http://localhost:8000`)**: Frontend communicates seamlessly with real API endpoints with server sessions and SQLite persistence.
   - **When on Static Showcase (GitHub Pages)**: Surfaces a non-dismissible demo notice, disables real credential input, and provides pre-configured synthetic guided personas.
3. **Local Email Inbox**:
   - Provide `GET /api/dev/inbox` where all verification tokens and password resets land in local development mode.
4. **Deterministic Provider Sandboxes**:
   - Formalize all 7 sandbox adapters (PAN, Aadhaar, Bank, Class 10, Face Match, IRDAI Registry, Malware) with explicit "Sandbox" labeling.
5. **Dynamic Analytics & Health Endpoints**:
   - Wire the Analytics and Verification dashboards directly to real database queries.
