# Security review and release limits

Implemented controls: scrypt salted passwords; configured HS256 signing; header/issuer/audience/expiry validation; persisted role/token-version checks; browser HttpOnly cookies; refresh-family binding/rotation/reuse detection; logout/reset revocation; single-use reset digests; exact Origin CSRF/CORS controls; size caps; central ownership/assignment/state policies; separate admin authority; minimised progress schema; applicant-safe response filtering; immutable audit triggers; pseudonymous analytics; filtered technical logging; persistent daily AI ceiling; deterministic upstream fallback.

Tests exercise wrong credentials, tampering, expiry, rotation/reuse, logout/reset access invalidation, cookie lifecycle, role manipulation, cross-owner denial, unassigned reviewers, admin-only assignment, appeal ownership, immutable audit, private-field minimisation, client-context/source manipulation, prompt injection, ID-number refusal, origin controls and rate limits. See executed logs and TEST_REPORT.md. This is not an independent penetration test.

## Deployment gates and known limits

- Use HTTPS, a unique signing secret, durable SQLite volume, backup/restore and restricted filesystem permissions. Local `.local/` credentials/data are ignored and must never be bundled or published.
- The SQLite implementation and rate controls target one API instance. Multi-instance deployment needs shared quotas/database coordination.
- The frontend account workspace receives only minimised metadata. It cannot validate original identity images that were never stored. All external verification remains simulated.
- The inherited demo role selector exposes local synthetic demo views. It confers no account API role. Accounts receive separate local-save namespaces.
- Prompt/output filters reduce risk but cannot prove a live model's factual correctness. Unverified manual claims stay flagged; no legal-currentness claim is made.
- Recovery supports trusted CLI and optional TLS SMTP; actual SMTP delivery and mailbox ownership are not verified here. No MFA or email verification was added.
- Browser speech recognition may use the browser vendor's service; audio is not stored by PolicyNest. Device permissions/voice quality require real-device testing.
- Append-only SQL triggers protect normal application operations, not a privileged database administrator editing the file.
- Public health reports configuration only. Current live proxy reports `llm:false`; no actual live AI response is claimed.
