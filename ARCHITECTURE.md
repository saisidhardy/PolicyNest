# PolicyNest architecture

The inherited application remains `policynest_mvp/PolicyNest.html`: CSS, markup and vanilla JavaScript. `build_site.py` wraps it into `site/index.html`, copies OCR/PDF workers and WASM, generates the applicant-safe rulebook corpus, and copies the local Web Vitals bundle. No frontend framework was introduced.

The Python `copilot_api/main.py` service now hosts authentication, minimised account progress, assignments, appeals, policy assistance and reporting. SQLite is selected by `POLICYNEST_DB_PATH`; local storage is `.local/policynest.sqlite3`. Connections are transaction-scoped and closed explicitly. Schema creation/additive migrations are idempotent. This deployment supports one service instance with a durable local volume; it is not a multi-instance database architecture.

## Boundaries

| Component | Responsibility |
|---|---|
| Protected engine block | Existing deterministic decision logic, unchanged SHA-256 |
| Browser OCR | Raw files, images and OCR remain on device |
| `application_state.py` | Fixed-schema progress, document statuses/versions and issue codes; no OCR or ID fields |
| `auth.py` | Users, scrypt passwords, JWTs, rotating refresh families, single-use reset tokens |
| `policy.py` | Identity, role, owner, assignment, action, sensitivity and state decisions |
| `workflows.py` | Account cases, assignment history, appeals, reviewer notes/decisions, immutable audit events |
| `rag.py` / `embeddings.mjs` | Local hybrid keyword/vector retrieval and citation metadata |
| `telemetry.py` | Separate technical measurements and pseudonymous business events |
| `recovery.py` | Optional TLS SMTP recovery; trusted CLI recovery is also available |

Account progress is explicitly device-reported demonstration evidence. A signed request authenticates the owner; it does not make uploaded-document findings externally verified. Reviewer decisions are separate persisted case records. No raw identity evidence is stored server-side, so reviewers see metadata and reported findings rather than original images.

## Storage

Tables: `users`, `refresh_tokens`, `reset_tokens`, `application_snapshots`, `cases`, `assignment_history`, `appeals`, `review_notes`, `audit_events`, `technical`, `frontend_metrics`, `business_events`, `ai_daily_usage`. Audit-event updates/deletes are rejected by SQLite triggers. Account-scoped browser saves use `pn-onboarding-user-<id>`; unauthenticated demo progress uses the original key. Account switching clears in-memory data before loading that account's consented local save.

The applicant can separately consent to account sync and to product/performance measurements. Registration alone does not upload document status. The existing local save consent remains separate. The model receives retrieved policy passages and a minimised owned snapshot, never unrestricted database access.
