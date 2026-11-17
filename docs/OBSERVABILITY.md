# PolicyNest Technical Observability & Health Monitoring

**Architecture:** Distributed Structured JSON Logging, Request Correlation IDs, Error Boundaries  

---

## 1. Structured Logging & Redaction Standard

Every server transaction emits structured JSON logs formatted as:
```json
{
  "timestamp": "2026-11-17T07:15:20.123Z",
  "level": "INFO",
  "correlation_id": "req_a1b2c3d4e5f6",
  "actor_id": 104,
  "role": "reviewer",
  "action": "REVIEW_DECIDE_CASE",
  "resource_id": "PN-2026-00101",
  "status": "KYC_APPROVED",
  "duration_ms": 14.2
}
```

### Strict Redaction Standard (NIST / DPDP Act):
The logging middleware automatically redacts sensitive parameters using regex filters:
- **Passwords / Tokens:** Replaced with `[REDACTED_SECRET]`
- **PAN:** Replaced with `ABCDE****F`
- **Aadhaar:** Replaced with `XXXXXXXX1234`
- **Bank Accounts:** Replaced with `••••••••5678`
- **Document Blobs:** Excluded from logs; only SHA-256 storage keys recorded.

---

## 2. Health & Readiness Endpoints

1. **`GET /health`:**
   - Liveness probe. Returns HTTP 200 `{ "status": "ok", "timestamp": ... }`.
2. **`GET /readiness`:**
   - Readiness probe. Executes atomic database read check and confirms WAL lock availability.
3. **`GET /api/verification`:**
   - Deep diagnostic endpoint returning status of all 16 platform subsystems.

---

## 3. Client-Side Error Tracking & Telemetry

- **Frontend Error Boundary:** Global `window.addEventListener("error")` and `unhandledrejection` handlers catch script crashes and render an accessible, non-blocking notification without breaking navigation.
- **Web Vitals Integration:** Emits Largest Contentful Paint (LCP), Interaction to Next Paint (INP), and Cumulative Layout Shift (CLS) via `web-vitals.iife.js` directly into performance logs.
