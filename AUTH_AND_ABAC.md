# Authentication and authorisation

Registration always creates `applicant`. Reviewer, admin and ops roles are provisioned through the trusted CLI; applicants cannot set them in registration JSON. Passwords use a random 16-byte salt and scrypt (`N=16384,r=8,p=1`). Password length is 12–256 characters. Signing requires a configured 32+ character `JWT_SECRET`.

Browser login returns a public user object and HttpOnly `pn_access`/`pn_refresh` cookies. Cookies use `SameSite=Lax`, `/api` scope and `Secure` when `APP_NAME` is configured. Tokens are not put in localStorage or login JSON. HS256 JWT validation checks signature, header, issuer, audience, expiry, current role, persisted token version and, for browser sessions, active refresh family. Access defaults to one hour; refresh tokens expire after seven days.

Refresh tokens are stored only as SHA-256 digests. Rotation uses `BEGIN IMMEDIATE`; a consumed token cannot be replayed. Reuse revokes its family and invalidates existing access tokens. Logout invalidates access and refresh credentials. Password reset increments the token version and revokes all refresh tokens. The frontend serialises concurrent renewals to avoid accidental replay.

All state-changing API routes require an exact allowlisted Origin, which is the browser CSRF protection. `null` and unknown origins are rejected. Credentialed CORS is restricted to that same allowlist. Use HTTPS and `APP_NAME` in deployment. Local HTTP is intentionally supported on localhost.

## Recovery

`/api/auth/recover` returns the same neutral response for all addresses. Configured TLS SMTP sends a 15-minute, single-use reset link; tokens stay out of API responses/logs and use a URL fragment. Without delivery configuration, an administrator can run `admin.py reset-password --email ...` and enter a replacement password privately. SMTP delivery was not tested against a real mailbox.

## Central policy

Applicants may read/sync their own progress, ask about their own state and create appeals. Document-state updates are allowed only in DRAFT/NEEDS_MORE_INFO. Once a reviewer has approved KYC, only training/exam/certificate progress with unchanged document metadata can sync. Reviewers require current assignment for case reads, decisions and appeal resolution. Admin assignment is separately checked and is not granted to reviewers. Ops/admin may read aggregate reports. Services require explicit scopes; the LLM receives no service/reviewer identity.

HTTP self routes derive the user ID from authentication; they accept no owner parameter. Reviewer case IDs are fetched from SQLite and checked against current assignments. Account UI visibility is convenience only; protected access is enforced by the backend. The inherited demo role selector is still visibly labelled as a demo and grants no API permissions.

Limitations: there is no MFA/email verification, no production penetration-test claim, and no multi-node rate-limit coordination. Logout conservatively invalidates all access JWTs for the user. See SECURITY_REVIEW.md and executable tests for the actual coverage.
