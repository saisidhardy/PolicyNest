# PR #1 (Codex, Hardik Nagpal): what it adds, what is verified

**Reviewed:** 15 Nov 2026 by three parallel read-only verifiers (backend, frontend, retrieval and tooling). Each checked the PR's own documents against the code and ran the tests.

**PR:** commits `a408c03` and `202fea2`, merged on GitHub as `2c85473`: 60 files, about 5,000 lines.

**Live status:** none of it is deployed. https://policynest.embarko.app runs the audited pre-PR build plus the role switch.

## What the PR is

It moves PolicyNest from a serverless demo toward a product with a server:

- **Accounts:** scrypt passwords, HS256 JWTs in HttpOnly cookies, rotating refresh tokens, password reset.
- **Authorisation:** a central ownership, assignment and role policy.
- **Data:** a SQLite store; reviewer assignment by an admin; appeals; an immutable audit trail.
- **Copilot:** a new `/api/assistant` with hybrid keyword-plus-vector retrieval over an added "POSP manual".
- **Measurement:** consent-gated telemetry and business analytics, and a Web Vitals collector.
- **UI:** an account and workspace UI added to `PolicyNest.html`.
- **Docs:** `ARCHITECTURE.md`, `AUTH_AND_ABAC.md`, `REVIEWER_AND_APPEALS.md`, `ASSISTANT_AND_VOICE.md`, `RAG_ARCHITECTURE.md`, `SECURITY_REVIEW.md`, `OBSERVABILITY.md`, `BUSINESS_ANALYTICS.md`, `DEPLOYMENT_GUIDE.md`, `IMPLEMENTATION_TRACKER.md`, `CLAUDE_HANDOFF.md` and others.

This reverses the earlier "no accounts, no server store" decision (ADR 0003, `CLAUDE.md`). That decision now belongs to the team and should be recorded.

## Verified true (with executed evidence)

- **Engine:** untouched (hash `c206388747e8381e`); `tools/check_pack.py` ALL PASS; the build is reproducible.
- **Backend tests:** **32 of 32 pass** in a fresh virtual environment. They cover tamper, expiry, rotation and reuse, logout and reset invalidation, cookies, cross-owner denial, unassigned reviewers, admin-only assignment, appeal ownership, immutable audit, minimised snapshots, origin checks and rate limits.
- **Backend design matches the docs (19 claims true):**
  - scrypt (N=16384, r=8, p=1);
  - full JWT validation (header, issuer, audience, expiry, role, token version);
  - HttpOnly SameSite=Lax cookies;
  - exact-origin CSRF and CORS;
  - registration always creates an applicant;
  - only an admin assigns reviewers, and reviewers see only their assigned cases;
  - appeals refuse ID numbers;
  - audit-event triggers make the audit trail append-only.
- **Frontend (12 claims true):** the account dialog, workspace, appeal form and "Show next action" all exist. **On the static site with no API, they degrade gracefully:** no JS errors, and **T1–T10 pass 10/10**.
- **Old proxy still works:** with no `JWT_SECRET`, `main.py` still runs as the old stateless proxy.

## Not true, or only partly true

| Claim | Reality |
|---|---|
| Hybrid (vector) retrieval | The committed `rag_index.json` has **no vectors** (`embedding_model: null`), so retrieval is always keyword-only. `eval/out/rag_results.json` (24/24, "hybrid", 112 ms) came from a local index that is not in the repo. A keyword-only re-run also gives 24/24, but the eval's expected patterns are loose regexes. |
| "Full verification" | `eval/out/verification.json` shows **7 of 8** checks passing; the assistant browser test failed (exit 1), and its log is not in the repo. |
| `TEST_REPORT.md` | Cited in `SECURITY_REVIEW.md`, but it does not exist. |
| Telemetry consent | Enforced only in the browser. `/api/telemetry` is unauthenticated (only rate-limited), and `/api/events` accepts any signed-in user. |
| POSP manual as a source | Its source PDF is not in the repo, and the manual describes itself as synthesised. It **contradicts the rulebook and the app**: an exam pass mark of 35% (the app uses 50%) and passport-photo rules. The assistant can quote it with only an "unverified" prefix. |

## Defects and deployment risks found

1. **Assistant false refusal:** in no-key mode, "What is PAN?" returns the canned safe sentence, because the rulebook's format example `AAAAA9999A` trips the ID-number output filter.
2. **The proxy now needs a writable SQLite path.** If `auth._db()` fails, `_daily_left()` returns 0 and AI answers silently switch off.
3. **The proxy imports `rag_index.json`, `posp_manual.json` and `kb.json` at start-up.** The old deploy recipe would crash it, and could also bundle a local `policynest.sqlite3`.
4. **Production cookies are cross-origin** (`policynest.embarko.app` → `policynest-copilot.embarko.app`). That needs `SameSite=None; Secure` and credentialed CORS; the code uses `SameSite=Lax`, so sign-in would likely fail in production.
5. **The site now fires** `GET /api/auth/me` and `/api/health` on every load, plus a 5-second sync interval (idle unless signed in and opted in).
6. **The sidebar always shows** "Sign in" and "Account workspace", even when no account service exists (a UX and trust wrinkle).
7. **The build now expects `node_modules/web-vitals`** (`npm install`). `tools/test_integrated.mjs` hard-codes the Windows `.python-runtime`. `.idea/` is committed.
8. **Smaller issues:**
   - logout without a refresh cookie does not invalidate the access JWT;
   - appeals marked MORE_INFO or ESCALATED can be re-resolved;
   - CLI assignment records actor 0;
   - single-node only;
   - no MFA or email verification.

## What this means

- **Safe as is:** the merged code is safe on the current static deploy model; the app behaves as before when no account server is reachable.
- **Not deployable yet:** the server half needs durable storage, secrets, a cross-origin cookie setup and the fixes above, and the team should decide whether PolicyNest becomes a server product.
- **Before any deploy of PR #1:**
  - fix 1, 3 and 4;
  - decide on 6;
  - reconcile the POSP manual with the rulebook, or keep it out of applicant answers;
  - re-run T1–T10 and the backend tests.
