# PolicyNest Testing Strategy and Verification Matrix

## 1. Overview & Verification Strategy

PolicyNest employs a multi-tiered automated and manual verification strategy:
1. **Unit & Module Tests**: Cryptographic primitives, password hashing, session tokens, rate limiting, and schema migrations.
2. **Subsystem Integration Tests**: State machine transitions, document validation & OCR extraction, reviewer operations, training module completion, exam proctoring, certification issuance, and communications dispatches.
3. **End-to-End Operational Journeys**: 4 comprehensive user journeys validating all interactions across Applicant, Reviewer, and Admin personas.
4. **Security & Production Gate Audits**: Zero plaintext credential check, forbidden token scanner, CSP compliance, and CORS origin validation.

---

## 2. Automated Test Suite Matrix

| Test Suite File | Domain | Test Count | Key Verification Targets |
|---|---|---|---|
| `test_auth.py` | Auth & Sessions | 8 | Scrypt hashing, salt uniqueness, session TTL, anti-CSRF |
| `test_milestone1_security.py` | Security & RBAC | 12 | Policy rules, authorization policies, forbidden fallback rejection |
| `test_milestone2_persistence.py` | Database & WAL | 14 | Migration integrity, SQLite WAL mode, foreign keys, transaction rollback |
| `test_milestone3_documents.py` | Storage & Intake | 15 | Magic-byte checks, private directory isolation, malware scanner |
| `test_milestone4_review_ops.py` | Reviewer Queue | 14 | Case queue, assignments, correction requests, resubmissions |
| `test_milestone5_fraud.py` | Fraud Sentinel | 12 | Blacklist matching, risk scoring, duplicate prevention |
| `test_milestone6_training.py` | Training LMS | 12 | Heartbeat validation, 15h pacing, progress persistence |
| `test_milestone7_exam.py` | Exam Engine | 15 | Question bank randomization, scoring algorithm, 75% pass mark |
| `test_milestone8_certification.py` | Certification | 12 | Agreement execution, certificate minting, public QR verification |
| `test_milestone9_notifications.py` | Communications | 10 | Local outbox persistence, email/SMS template formatting |
| `test_milestone10_verification.py` | Subsystem Audit | 10 | 16 subsystem probes, QA seed/reset isolation |
| `test_e2e_journeys.py` | E2E Operational | 46 | 4 complete journeys (Applicant, Reviewer, Recovery, Cross-Role) |
| `test_portal.py` | REST API Routing | 41 | REST endpoints, parameter binding, payload validation |
| `test_assistant.py` | RAG Knowledge | 14 | Vector retrieval, BM25 indexing, prompt injection defense |
| **Total Test Count** | **All Modules** | **215** | **100% Pass Rate** |

---

## 3. Test Execution Commands

### Execute All Tests
```bash
python -m unittest discover -s policynest_mvp/copilot_api -p "test_*.py"
```

### Execute Specific Milestone Suite
```bash
# Test Core Authentication & Passwords
python -m unittest policynest_mvp/copilot_api/test_auth.py

# Test End-to-End Operational Journeys
python -m unittest policynest_mvp/copilot_api/test_e2e_journeys.py

# Test Subsystem Verification & QA Tooling
python -m unittest policynest_mvp/copilot_api/test_milestone10_verification.py
```

### Execute Production Bundle Gate
```bash
python tools/check_prod_build.py
```
*Verifies that zero forbidden tokens (`localStorage` user passwords, fake reviews, mock auto-registrations) exist in the production site distribution.*
