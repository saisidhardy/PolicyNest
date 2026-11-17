# PolicyNest Persona Authorization & Access Matrix

**Authorization Engine:** NIST SP 800-162 Attribute-Based Access Control (`copilot_api/policy.py`)  
**Server Authority:** Zero trust of client-provided roles or permissions  

---

## 1. Authoritative Persona Roster

| # | Persona | Role Code | Account Provisioning | MFA | Landing Page | Primary Data Scope |
|---|---|---|---|:---:|---|---|
| 1 | **Public Visitor** | `anonymous` | Self-directed landing access | No | `#welcome` | Public marketing, guidelines, public certificate verification |
| 2 | **POSP Applicant** | `applicant` | Self-registration (`/api/auth/register`) | Opt | `#dashboard` | Own application draft, documents, training, exam, cert |
| 3 | **Frontline Reviewer** | `reviewer` | Admin provisioned (`/api/admin/staff`) | Yes | `#review` | Assigned applicant dossiers, rework queue, defect notes |
| 4 | **Senior Reviewer** | `senior_reviewer` | Admin provisioned | Yes | `#review` | Escalated cases, applicant appeals, supervisor overrides |
| 5 | **Operations Admin** | `operations` | Admin provisioned | Yes | `#review` | Workload balancing, SLA tracking, queue reassignment |
| 6 | **Compliance Officer** | `compliance_officer` | Admin provisioned | Yes | `#audit` | Full audit trail inspection, regulatory audit pack export |
| 7 | **Fraud Investigator** | `fraud_investigator` | Admin provisioned | Yes | `#review` | Anomaly tickets, velocity limits, blacklists, fraud holds |
| 8 | **Technology Admin** | `tech_admin` | Admin provisioned | Yes | `#verification`| System health, DB migrations. **Zero document access** |
| 9 | **External Auditor** | `auditor` | Admin provisioned | Yes | `#audit` | Read-only tamper-evident compliance audit logs |
| 10| **Support Agent** | `support` | Admin provisioned | Yes | `#help` | User ticket context; **cannot approve or alter applications** |
| 11| **System Daemon** | `system` | Automated internal worker | N/A| Internal | Heartbeat monitors, batch timers, audit log sealer |

---

## 2. Multi-Role Capability Matrix

| Action / Capability | `applicant` | `reviewer` | `senior_reviewer` | `compliance` | `fraud` | `tech_admin` | `auditor` | `admin` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `application.read_own` | **ALLOW** | - | - | - | - | - | - | - |
| `application.read_assigned`| DENY | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | DENY | DENY | **ALLOW** |
| `application.read_other` | DENY | DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| `application.save_draft` | **ALLOW** (Own)| DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| `document.upload` | **ALLOW** (Own)| DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| `document.download_image`| **ALLOW** (Own)| **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | **DENY** | **DENY** | **DENY** |
| `review.claim` | DENY | **ALLOW** | **ALLOW** | DENY | DENY | DENY | DENY | **ALLOW** |
| `review.decide_kyc` | DENY | **ALLOW** | **ALLOW** | DENY | DENY | DENY | DENY | DENY |
| `review.decide_appeal` | DENY | DENY | **ALLOW** | DENY | DENY | DENY | DENY | DENY |
| `fraud.flag_hold` | DENY | **ALLOW** | **ALLOW** | DENY | **ALLOW** | DENY | DENY | DENY |
| `fraud.investigate_ring`| DENY | DENY | DENY | DENY | **ALLOW** | DENY | DENY | DENY |
| `training.update_time` | **ALLOW** (Clamp)| DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| `exam.submit_answers` | **ALLOW** (Own)| DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| `certificate.issue` | Server Only| Server Only| Server Only| Server Only| Server Only| Server Only| Server Only| Server Only|
| `certificate.verify` | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** |
| `audit.read_timeline` | **ALLOW** (Masked)| **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** | DENY | **ALLOW** | **ALLOW** |
| `compliance.export_pack`| DENY | DENY | DENY | **ALLOW** | DENY | DENY | **ALLOW** | **ALLOW** |
| `staff.provision` | DENY | DENY | DENY | DENY | DENY | DENY | DENY | **ALLOW** |

---

## 3. Privacy Boundary: Tech Admin & Auditor Isolation

In strict compliance with the **Data Protection by Design (DPDP Act 2023)** principle:
- Infrastructure operators (`tech_admin`) and financial auditors (`auditor`) have access to system metrics, schema migrations, and audit hashes.
- They are **cryptographically and programmatically forbidden** (`PermissionError: forbidden_for_role`) from viewing or downloading personal identity documents (PAN photos, Aadhaar cards, bank statements).
