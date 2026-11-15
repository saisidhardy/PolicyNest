# Execution tracker

Current committed baseline: a408c03. All subsequent changes are retained in the working tree.

| Workstream | Status | Evidence / exact next step |
|---|---|---|
| Engine baseline | Tested | 600/600 in-sample; hash c2063887; unchanged predictions |
| Authentication | In progress | scrypt/JWT/SQLite foundation; finish session rotation, revocation, recovery and execute tests |
| ABAC | In progress | policy.py and negative unit tests; integrate authoritative application state and assignments |
| PDF ingestion | Tested | Seven pages, 26 sections extracted using tools/ingest_posp_manual.mjs |
| Semantic/hybrid retrieval | Not started | Existing production retrieval remains BM25 |
| Reviewer assignments / appeals | Not started | Requires persistent schema, policies, APIs and UI |
| Auth UI/session integration | Not started | Preserve existing demo role switch |
| Authorised assistant state | Not started | Client context currently supplied to Copilot |
| Voice / visual guidance | Not started | Existing read-aloud and proactive prompts inherited |
| Observability / analytics | Not started | Define schema and retention before collection |
| Python runtime | Tested | Isolated official 3.12.10 embedded runtime works in .python-runtime |
| Backend regression | Tested | 22 auth/ABAC/Copilot tests pass; SQLite connection leak fixed |
| Static pack / build | Tested | check_pack.py ALL PASS including engine hash, JS syntax, banned phrases and build |
| Browser regression | In progress | Python available; Playwright dependency/browser still needed |
| Human studies / independent labels | Blocked | Requires actual participants and independent human labels |
| Deployment | Blocked | Explicit deployment approval and durable storage configuration required |

Last completed: refresh rotation/reuse-family revocation, refresh logout revocation, single-use reset store and HTTP endpoints added. Tests: 22 passed; static pack ALL PASS. Access JWTs still lack session revocation linkage; browser cookie/session integration pending. Recovery delivery deliberately returns a neutral support response until a trusted delivery adapter exists. Token APIs currently return JSON; no browser token storage implemented.

Next: bind JWTs to revocable server sessions, validate issuer/audience/header, implement HttpOnly cookie and CSRF session flows, then add HTTP lifecycle integration tests. No production changes authorised.

## Latest execution checkpoint

Assistant increment: visual next-action/focus controls, optional voice input/read/stop, language selector and confirmed persistent appeal form added to existing Copilot. Server citations now displayed. `node tools/test_assistant.mjs` PASS in headless installed browser (focus, signed-out appeal gate, fallback, no JS page errors). Backend 27 tests PASS; build/static pack ALL PASS. See ASSISTANT_AND_VOICE.md for unfinished authenticated context/manual retrieval/evidence-linkage and device testing. Changes remain uncommitted.

- Access JWTs now carry a persisted token version; logout, password reset and refresh reuse invalidate access tokens. JWT header, issuer and audience validated.
- Browser sessions now use HttpOnly SameSite=Lax cookies; production APP_NAME adds Secure. Exact Origin allowlist protects POST requests; credentialed CORS enabled. Tokens are absent from login JSON.
- Frontend account dialog added using existing mbox/btn styles: register, sign in, sign out, neutral recovery and renewal. Visual browser validation still pending. Demo data is not automatically uploaded or associated with an account.
- workflows.py adds cases, reviewer assignments, appeals and immutable audit events. Routes expose own case/appeals, assigned queue, admin assignment and reviewer resolution. UI integration remains outstanding.
- Auth/ABAC/Copilot suite passed 26 tests before workflow addition. Workflow security test also passed; final deduplicated full-suite result recorded in tool output.
- Static pack continues passing with engine unchanged. Runtime blocker is resolved. Next: finish reviewer/appeal UI, trusted admin CLI, snapshot schema and server-authoritative state; then semantic RAG and instrumentation.
