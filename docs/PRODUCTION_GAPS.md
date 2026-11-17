# PolicyNest Production Gaps and Commercial Dependencies

## 1. Executive Summary

PolicyNest operates locally as a completely functional, production-shaped application with real local SQLite persistence, Scrypt password hashing, server sessions, RBAC/ABAC authorization, and deterministic sandbox adapters.

To transition from this local working model to live commercial operation under IRDAI regulations, specific external services, commercial agreements, and infrastructure must be provisioned. This document provides an honest, rigorous accounting of those external dependencies.

---

## 2. Commercial & Regulatory External Dependencies

| Capability | Current Local / Sandbox Implementation | Commercial / Production Requirement | Estimated Lead Time |
|---|---|---|---|
| **PAN Verification** | `PanVerificationProvider` (Deterministic Sandbox) | NSDL / Protean or UTIITSL API subscription agreement; static IP whitelisting | 2–4 weeks |
| **Aadhaar e-KYC** | `AadhaarKycProvider` (Deterministic Sandbox) | UIDAI AUA / KUA (Authentication / KYC User Agency) license or licensed Sub-KUA partner (e.g. Karza, Signzy, Bureau) | 4–8 weeks |
| **Bank Penny-Drop** | `BankPennyDropProvider` (Deterministic Sandbox) | NPCI IMPS direct integration or certified payments aggregator (RazorpayX, Cashfree, Setu) | 1–3 weeks |
| **IRDAI Central Registry** | `IrdaiRegistryProvider` (Deterministic Sandbox) | IRDAI BAP / Agent Portal API credentials; corporate agency registration code | 4–6 weeks |
| **Biometric Face Match** | `FaceMatchProvider` (Deterministic Sandbox) | Certified liveness & face comparison vendor (e.g. AWS Rekognition, FacePlusPlus, HyperVerge) | 1–2 weeks |
| **Transactional Email** | `communication_dispatches` (Local In-Database Inbox) | Enterprise SMTP / transactional email service (Amazon SES, SendGrid, Postmark) with DKIM/DMARC | 1–3 days |
| **SMS OTP Delivery** | `communication_dispatches` (Local In-Database Inbox) | DLT-registered SMS gateway (Twilio, Gupshup, ValueFirst) with approved IRDAI DLT templates | 1–2 weeks |
| **Cloud Object Storage** | `documents_storage/` (Private local filesystem) | S3-compatible private bucket (AWS S3, Google Cloud Storage) with server-side KMS encryption and signed URLs | 1–2 days |
| **Production Database** | `policynest.sqlite3` (Local SQLite with WAL mode) | Managed PostgreSQL (AWS RDS, Neon, Supabase) with automated point-in-time recovery (PITR) | 1–2 days |
| **WAF & DDoS Defense** | Built-in Python Token-Bucket Rate Limiter | Cloudflare Enterprise / AWS WAF with rate-limiting rules and bot mitigation | 1–2 days |
| **Error Monitoring** | Structured JSON logs | Sentry / Datadog APM for real-time exception tracking and alerting | 1 day |

---

## 3. Security & Operational Hardening Checklist for Production

Before promoting from `LOCAL_DEVELOPMENT` / `DEMO` to `PRODUCTION`:
1. **Environment Flag**: Set `POLICYNEST_ENV=PRODUCTION` in `.env`. The backend strictly disables QA seed/reset routes and enforces production secrets.
2. **Secret Keys**: Replace temporary development keys (`JWT_SECRET`) with high-entropy 256-bit cryptographic secrets managed via AWS Secrets Manager or HashiCorp Vault.
3. **TLS & HTTPS**: Terminate TLS at the load balancer or ingress with TLS 1.3 only and HSTS headers (`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`).
4. **Data at Rest**: Ensure volume containing database and documents is encrypted at rest using AES-256-GCM.
5. **Backups**: Configure automated daily snapshots with offsite replica retention for 7 years to comply with IRDAI regulatory document retention rules.
