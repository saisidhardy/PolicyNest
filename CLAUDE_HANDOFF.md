# Work-in-progress handover

This is an interruption checkpoint, not final delivery. Baseline commit a408c03 remains the last commit; inspect git status for all preserved subsequent changes.

## Runtime and executed checks

An isolated official Python 3.12.10 embedded runtime is installed in ignored `.python-runtime/`. Run it explicitly; it does not modify the system installation.

Backend test command:

    .python-runtime/python.exe -c "import sys,unittest; sys.path.insert(0,'policynest_mvp/copilot_api'); s=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ['test_auth','test_policy','test_main']); r=unittest.TextTestRunner().run(s);sys.exit(not r.wasSuccessful())"

Actual result: 22 tests passed. Static pack command `.python-runtime/python.exe tools/check_pack.py`: ALL PASS, including generated build and unchanged pinned engine hash. Browser T1–T10 not yet executed.

## New modules

- `copilot_api/auth.py`: SQLite identity, scrypt passwords, expiring HS256 JWTs, owner snapshots; hashed refresh-token families with atomic rotation, reuse-family revocation; hashed single-use 15-minute reset tokens; reset revokes refresh tokens. Fixed SQLite connection lifecycle after an executed Windows locking failure.
- `copilot_api/policy.py`: basic ownership, assignment, role, sensitivity and state decisions; only self snapshot routes integrated so far.
- `test_auth.py`, `test_policy.py`: executed unit coverage; existing Copilot contracts continue passing.
- `tools/ingest_posp_manual.mjs`, `copilot_api/posp_manual.json`: seven-page extraction into 26 page-aware sections with source metadata. Semantic retrieval is not implemented or wired into Copilot.
- `.env.example`: variable names/placeholders for JWT secret, TTL and database path. Values never inspected.

## Security gaps that must be fixed before release

JWTs are not yet linked to revocable server sessions, so logout/password reset currently revoke refresh tokens but existing access JWTs survive until expiry. Cookie/CSRF and frontend session flow are absent. Recovery HTTP response is enumeration-neutral but uses support rather than automated delivery. Reviewer assignments, appeals, authoritative application state and protected reviewer APIs remain absent. Snapshot storage currently accepts arbitrary JSON and needs strict minimisation/schema checks before UI integration. JWT header/issuer/audience validation needs completion. Registration must check auth configuration before inserting a user. Do not deploy this increment as complete authentication.

## Remaining product scope

See IMPLEMENTATION_TRACKER.md. Reviewer/appeals, hybrid semantic RAG, authorised assistant state, visual/voice upgrades, observability, business analytics, complete UI integration, browser tests and final documentation remain unfinished. Existing main app UI and engine are preserved. Build regenerated site/index.html to include committed F-11 save minimisation. Durable hosting storage and recovery-delivery provider require configuration before deployment. Human studies and independent labels require actual human participation.
