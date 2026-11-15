# Production applicant portal: Phase 1 audit and plan

15 Nov 2026. Brief: "Embarko's comprehensive POSP onboarding journey inside Railway's calmer, authenticated, production-grade applicant shell" (workstreams A–Y).

**User decisions (15 Nov):**

- **Server data:** details and progress are kept. Photos, OCR text, full PAN, full Aadhaar and the full bank account number are **never** stored on the server.
- **Two sites:** a production portal (`policynest`) and a demo site (`policynest-demo`), built from the same code with a build flag.

## 1. Architecture as found (inspected, run)

| Area | Implementation | Reuse |
|---|---|---|
| Framework | None. One file, `policynest_mvp/PolicyNest.html` (2,565 lines: CSS, markup, one IIFE with vanilla JS), wrapped by `build_site.py` into `site/index.html` | Keep (ADR 0007). No framework is introduced |
| Routing | Hash routes `#dashboard #apply #review #evaluation #audit`; `show(v)`, `fromHash()`, `HASH`, `NAV`; steps inside `#apply` are `S.step` and `S.dpage` | Extend with `#home #documents #training #exam #certificate #notifications #history #account #help` |
| State | One object `S`; `fresh()`, `render()`, `persist()`/`restore()`/`savedCopy()` (consented localStorage `pn-onboarding-v1`) | Keep the local copy as offline fallback only |
| Engine | Pure block `ENGINE:START`–`END`, SHA-256 pinned (`c2063887…`), scored on 600 cases | **Untouched** |
| Auth (PR #1) | `copilot_api/auth.py`: scrypt, HS256 JWT in HttpOnly SameSite=Lax cookies, rotating refresh tokens; `policy.py` (ABAC); `workflows.py` (cases, assignment, appeals, audit); account dialog plus workspace in the HTML (`ACCOUNT`, `syncProgress`, `workspaceLoad`) | **Integrate; no parallel auth.** Site and API share the site `embarko.app`, which is not on the Public Suffix List, so Lax cookies flow |
| API | `copilot_api/main.py`: `/api/auth/*`, `/api/applications/me`, `/api/cases/me`, `/api/appeals`, `/api/reviewer/queue`, `/api/admin/assign`, `/api/assistant`, `/api/copilot`, `/api/health`, `/api/ready`, `/api/events`, `/api/telemetry` | Extend |
| Storage | SQLite at `POLICYNEST_DB_PATH`. Embarko server apps get a durable `DATA_DIR` that survives redeploys; it is **not backed up** | Default the DB to `DATA_DIR` |
| Styling | CSS tokens on `:root` in two themes; bento look v3 | Keep the Embarko look |
| Tests | `tools/check_pack.py` (engine hash, JS syntax, banned phrases, build); `tools/t1_t10.py` (Playwright); backend `unittest` (32 pass); `eval/run_eval.js` | Extend: Node `node:test` for the new pure model, backend tests, Playwright e2e |
| Roles | Server roles applicant, reviewer, admin, ops (`admin.py provision`); the demo "View as" switch is client-only | Production uses server roles; the switch exists only in the demo build |

## 2. Gaps against the brief

- **Identity:** no shell identity, status, application reference, save state or next action in one place.
- **Saving:** the server stores only a minimised snapshot, with no details, versioning or 409 protection.
- **Updates:** no notifications and no applicant timeline.
- **Status:** no normalised applicant status model or next-action resolver; status logic is scattered.
- **Language:** no i18n (Hindi exists only in follow-up messages).
- **Navigation and demo wording:** staff views show for everyone in the default build; demo wording and controls show in production.
- **Sitting:** the 30-minute countdown and its urgency.
- **Mobile:** the Embarko badge covers the CTA; the navigation stacks into rows; the first phone screen has no next action.

## 3. Architecture decisions

1. **One pure, testable model region** `/* MODEL:START */ … /* MODEL:END */` in `PolicyNest.html`, holding:
   - JSDoc types for ApplicantProfile, Application, ApplicationStatus, JourneyStage, ResumePosition, SaveState, DocumentRequirement, DocumentStatus, Notification, TimelineEvent, TrainingProgress, ExamStatus, CertificateStatus and UserRole;
   - `STATUS` (label key, description key, tone, icon, needs-action, next event, timeline);
   - `STAGES`;
   - `statusOf(S)`, `nextAction(S)`, `resumePosition(S)` and `progressModel(S)` (journey, form, documents, compliance, training, exam, certificate, kept separate);
   - `can(role, action)`;
   - `applicantTimeline(events)`;
   - `I18N {en, hi}`, `t(key, params)` with named placeholders and whole sentences, and a glossary.

   No DOM, so `tools/test_model.mjs` extracts it and tests it with `node --test`, the same pattern as the engine.
2. **Server holds the source of truth when signed in.** The local consented copy is a fallback and an offline queue only.
   - Optimistic concurrency: every save sends `version`; the server returns 409 with its copy when stale.
   - Saves are debounced (1.5 s after the last meaningful change).
   - Visible states: Saving…, Saved, Save failed (Retry), Offline changes pending.
3. **Application reference** `PN-YYYY-NNNNN`: generated server-side (random, unique, retried on collision) on first creation, stable for the application's life, and never derived from PAN, Aadhaar, phone or email. Signed-out demo sessions show a local reference labelled "not yet registered".
4. **Notifications and timeline are server records**, created by the server from allowlisted applicant-safe event keys. They are stored as keys plus non-sensitive params and translated on the client. Internal and staff events never enter them.
5. **Builds:**
   - `build_site.py --mode prod` writes `site/`. DEMO is false: no demo controls, specimens, "View as" switch or "this demo" wording. Staff views need a signed-in staff role (server-enforced for data; the client shows an unauthorised state).
   - `--mode demo` writes `site-demo/` with today's demo tools.
   - Honesty: simulated external checks stay disclosed in "How document checks work" (progressive disclosure, not banners).
6. **Timer:** the countdown, expiry and leave-screen warnings are removed and replaced with "Most applicants complete details and document upload in about 30 minutes." Save and exit is kept. No security timeout is added (none is required); the session expiry is handled by the refresh token.
7. **Hosting badge:** not hidden (the docs give no sanctioned way). Layout padding keeps it clear of the CTA, Copilot and bottom navigation.

## 4. API contract (new or changed; all JSON, cookie-authenticated, exact-Origin POST/PUT/PATCH)

| Route | Request | Response |
|---|---|---|
| `GET /api/me` | — | `{user:{id,email,display_name,role,email_verified,mobile_verified,mobile_masked,language}}`, or 401 |
| `PATCH /api/me` | `{display_name?, mobile?, language?}` (`en`/`hi`) | `{user}` |
| `POST /api/applications/me` | `{}` (idempotent create) | `{application}` (the existing one if present; UNIQUE on user) |
| `GET /api/applications/me` | — | `{application:{reference,version,status,details,progress,updated_at}}`, or 404 if none |
| `PUT /api/applications/me` | `{version, details, progress}` | 200 `{version,updated_at}`, or **409** `{error:"stale",application}` |
| `POST /api/applications/me/events` | `{events:[{key,stage?,doc?,t}]}` (allowlisted keys) | `{accepted:n}`; the server writes timeline rows and derived notifications |
| `GET /api/applications/me/timeline` | — | `{items:[{id,t,actor:"you"\|"policynest"\|"reviewer",key,stage?,doc?}]}` |
| `GET /api/notifications` | `?limit=` | `{items:[{id,type,key,stage?,doc?,action?,read,created_at,reference}],unread}` |
| `POST /api/notifications/read` | `{ids:[…]}` or `{all:true}` | `{unread}` |

**`details` (allow-listed):** `name, dob, mobile, email, state, city, education, ifsc, aadhaar4, pan_last4, acct_last4, language`. A full PAN or full account number is refused with 400.

**`progress` (allow-listed):**

- `stage, dpage, doc_index, resume{stage,page,doc,milestone,action,t}`;
- `documents{slot:{status,version,issues[]}}`;
- `decision, round, training{modules[],hours}, exam{score,passed,attempts,retake_at}, certificate{code,issued_at,seal}`.

## 5. Delivery (one writer at a time on `PolicyNest.html`; backend in parallel)

| Lane | Scope | Files |
|---|---|---|
| P2 model | MODEL region, i18n core with English and Hindi strings, node tests | `PolicyNest.html` (new region only), `tools/test_model.mjs` |
| BE | Contract above; DB at `DATA_DIR`; references; versioned saves and 409; notifications and timeline; profile; fixes (the PAN-example false refusal, start-up robustness, proxy packaging script that excludes `*.sqlite3` and `.env*`); tests | `copilot_api/*`, `tools/package_proxy.py` |
| P3+4 shell and dashboard | Identity bar, account menu, reference with copy, status, last saved, language switch, role-aware navigation, calm dashboard with one CTA and progressive disclosure | `PolicyNest.html` |
| P5 continuity | Save engine (debounce, versions, 409 merge, offline queue, retry); notification centre; timeline; account and profile screen; resume routing | `PolicyNest.html` |
| P6 production | Mobile bottom navigation, safe areas around Copilot and badge, 44 px targets, a11y, Hindi pass, prod/demo builds, timer rework, trust disclosures | `PolicyNest.html`, `build_site.py` |
| P7 verify | Unit, backend, e2e (applicant, reviewer and admin; cross-device; i18n; mobile sizes; 200% zoom; keyboard; sensitive-data scan; prod hides demo), screenshots, report | `tools/*`, `planning/` |

The engine hash must stay `c2063887…`, `check_pack` must pass, and T1–T10 must pass on the demo build after every lane.
