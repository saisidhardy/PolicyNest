# PolicyNest Product Analytics Privacy & Data Redaction Standard

**Governing Standard:** Digital Personal Data Protection (DPDP) Act 2023  
**Invariant:** Analytics data must NEVER contain identifiable personal data or biometric signals.

---

## 1. Absolute Blacklist (Forbidden Properties)

The analytics engine rejects and drops any event containing any of the following keys or values:
- `name`, `full_name`, `applicant_name`, `first_name`, `last_name`
- `email`, `email_address`, `recipient`
- `phone`, `mobile`, `contact_number`
- `address`, `address_line1`, `pincode`, `city`
- `pan`, `aadhaar`, `bank_account`, `ifsc`
- `file_bytes`, `content_base64`, `image_data`, `ocr_text`
- `password`, `token`, `secret`, `jwt`
- `answers`, `exam_choices`
- `reviewer_note`, `internal_comment`

---

## 2. In-Memory Sanitization & Redaction Layer

Before any analytics event leaves the client:
```javascript
function sanitizeEventPayload(payload) {
  var clean = {};
  var BANNED_KEYS = /name|email|mobile|phone|pan|aadhaar|acct|bank|pass|token|secret|ocr|text|note/i;
  for (var k in payload) {
    if (!BANNED_KEYS.test(k)) {
      var val = payload[k];
      if (typeof val === "string" && (val.length > 100 || /\d{10,12}/.test(val))) {
        continue; // Discard strings that resemble phone/aadhaar
      }
      clean[k] = val;
    }
  }
  return clean;
}
```

---

## 3. Consent Management

- Tracking is **opt-in** on this device (`CONS.analytics === true`).
- A persistent toggle is provided in the applicant profile settings and footer: **"Product Analytics (Anonymous)"**.
- If disabled, zero network dispatches are generated.
- Analytics failures are strictly non-blocking: network dropouts, ad-blockers, or server 500s on the analytics endpoint never interrupt applicant onboarding or form submissions.
