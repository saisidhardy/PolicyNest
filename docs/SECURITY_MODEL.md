# PolicyNest Security Architecture & Threat Model

This document outlines the security architecture, authorization policy model, cryptographic invariants, and defensive controls implemented across the PolicyNest platform.

---

## 1. Threat Model & Trust Boundaries

PolicyNest operates across three distinct security domains:
1. **Client Browser Boundary (Untrusted):**
   Runs applicant and staff web interfaces. Zero security logic, role checks, or eligibility transitions trust client state. Every state change requires server-authoritative validation.
2. **Application & API Gateway Layer (Trusted):**
   Enforces HTTP security headers, rate limiting, progressive account lockouts, CSRF protection, and NIST SP 800-162 Attribute-Based Access Control (ABAC).
3. **Data & Secret Storage Boundary (Isolated):**
   SQLite 3 with WAL mode and foreign key constraints. Cryptographic keys (`JWT_SECRET`, HMAC signing secrets) reside exclusively in server environment variables. Zero credentials ship to client bundles.

---

## 2. 11-Tier NIST SP 800-162 ABAC Model

PolicyNest implements fine-grained Attribute-Based Access Control governed by `policy.allows(actor, action, resource)`.

### Roles & Responsibilities:
1. **`applicant`**: Self-service onboarding, document upload, training module completion, exam taking, agreement signing, certificate retrieval, and dispute/appeal submission. Strictly isolated to own resources.
2. **`reviewer`**: Frontline underwriting operations. Claims cases, inspects dossiers, cites IRDAI rules, requests changes, and approves compliant KYC. Cannot access unassigned cases or fraud-restricted records.
3. **`senior_reviewer`**: Underwriting escalation authority. Resolves escalated cases, decides applicant appeals, and oversees complex name/identity discrepancies.
4. **`operations`**: Operational supervisor managing queue balancing and turnaround SLA monitoring.
5. **`compliance_officer`**: Regulatory oversight authority. Inspects full audit trails, exports regulatory audit packs, and audits decision logs.
6. **`fraud_investigator`**: Specialized fraud desk analyst. Manages fraud holds, investigates device fingerprint rings, and inspects restricted anomaly cases.
7. **`tech_admin`**: Infrastructure operator. Manages feature flags, provider sandbox modes, and database maintenance. **Strictly forbidden from viewing or downloading applicant identity documents (Privacy Guard).**
8. **`auditor`**: External/independent inspector. Read-only access to tamper-evident audit logs and compliance packs. Forbidden from modifying application state or viewing raw unmasked PII.
9. **`admin`**: System administrator. Provisions staff accounts, assigns roles, and manages platform configuration. Cannot bypass deterministic underwriting rules.
10. **`system`**: Automated worker processes (background timers, heartbeat checks, scheduled reports).
11. **`anonymous`**: Unauthenticated public visitor. Access is restricted to public landing pages and the zero-auth public certificate verification endpoint (`/api/certificates/verify/<id>`).

---

## 3. Cryptographic Standards & Integrity

### Password Hashing:
- Uses `scrypt` (or `Argon2id` when compiled) with cryptographic salt and minimum 12-character passphrase enforcement.
- Plaintext passwords are wiped immediately upon verification.

### Digital Certificate Signature:
Every issued POSP Appointment Certificate carries a deterministic HMAC-SHA256 signature calculated across:
```
signature = HMAC_SHA256(
    key = JWT_SECRET,
    data = cert_number + "|" + user_id + "|" + posp_name + "|" + pan_masked + "|" + issued_at + "|" + valid_until + "|" + lines_of_business
)
```
Any tampering with stored database rows immediately fails signature validation upon verification.

### Compliance Audit Pack Hash Chain:
The regulatory compliance pack aggregates all historical audit rows, verifies sequential row hashes, and stamps the entire archive with an authoritative SHA-256 integrity digest for regulatory submission.

---

## 4. Defensive Controls & Anti-Abuse Measures

### 1. Invariant: Anti-Accusation Protection
In strict adherence to IRDAI Guidelines and DPDP Act fair processing principles, applicants are **never** shown internal fraud labels, suspicion scores, risk triggers, or derogatory messages. If an application is held for review, the applicant receives neutral, constructive instructions (e.g., *"Your documents are undergoing standard compliance verification"*).

### 2. Anti-Enumeration Protection
- Password reset endpoints return an identical HTTP 202 Accepted response regardless of whether the submitted email address exists in the user registry.
- Registration endpoints reject duplicate accounts without disclosing additional profile metadata.

### 3. Session Revocation on Security Events
- Password changes, administrative account suspension, and reset token consumption immediately revoke all existing active session tokens for that account.

### 4. Zero Unmasked PII Invariant
- Aadhaar numbers are masked to `XXXXXXXX1234` immediately upon capture. Full 12-digit numbers are never stored.
- Bank account numbers are masked to `••••••••5678`.
- PAN cards are masked in all staff logs and public views to `ABCDE****F`.
