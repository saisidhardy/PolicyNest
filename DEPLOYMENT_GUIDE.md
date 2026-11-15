# Local execution and deployment prerequisites

From repository root on this Windows workspace:

    npm install
    .python-runtime/python.exe -m pip install -r policynest_mvp/copilot_api/requirements.txt playwright
    .python-runtime/python.exe policynest_mvp/build_site.py
    .python-runtime/python.exe tools/run_local.py

Open http://localhost:8000. The API listens on http://localhost:8787. The launcher creates an ignored local signing key and SQLite database and starts both services. It disables model calls by default and uses local retrieval. `--ai` opts into a provider already configured in environment variables. On another machine use a normal supported Python 3.12 installation instead of `.python-runtime/python.exe`; the embedded runtime itself is not committed.

Create a reviewer/admin/ops account privately:

    .python-runtime/python.exe policynest_mvp/copilot_api/admin.py provision --email reviewer@example.test --role reviewer
    .python-runtime/python.exe policynest_mvp/copilot_api/admin.py cases
    .python-runtime/python.exe policynest_mvp/copilot_api/admin.py assign --case PN-... --reviewer 1
    .python-runtime/python.exe policynest_mvp/copilot_api/admin.py reset-password --email applicant@example.test

Passwords are prompted, not command-line arguments. These sample addresses are instructions, not pre-created credentials.

Rebuild retrieval after corpus changes:

    node tools/ingest_posp_manual.mjs "path/to/POSP RAG System Knowledge Base & Policy Manual.pdf" policynest_mvp/copilot_api/posp_manual.json
    .python-runtime/python.exe policynest_mvp/copilot_api/rag.py prepare
    node policynest_mvp/copilot_api/embeddings.mjs index policynest_mvp/copilot_api/rag_index.json policynest_mvp/copilot_api/rag_index.json

Initial model indexing downloads the public MiniLM weights. Normal query embeddings are local. Without available weights/Node support, retrieval discloses keyword fallback.

Verification:

    .python-runtime/python.exe tools/verify.py --browser

Keep the local server running for browser tests. Logs go to ignored `test-results/`; machine-readable results go to `eval/out/verification.json`. Python Playwright uses installed Edge/Chrome when bundled Chromium is absent.

## Production

No deployment has been performed or authorised for these changes. The old proxy deployment bundle alone is insufficient for hybrid retrieval: package metadata, Node runtime/dependencies and model weights must be available alongside Python/API modules. Configure durable database storage, HTTPS, exact origin allowlist, `APP_NAME`, signing secret, budgets and optional SMTP. Do not include `.env`, `.local`, test databases, credentials or protected specimens in bundles. Validate `/api/ready`, cookie/CORS behaviour, model cache loading and backup restore in staging before requesting approval to deploy.

Environment names: `JWT_SECRET`, `JWT_TTL_SECONDS`, `POLICYNEST_DB_PATH`, `ANTHROPIC_API_KEY`, `COPILOT_MODEL`, `COPILOT_EFFORT`, `COPILOT_ORIGINS`, `COPILOT_GLOBAL_PER_MIN`, `COPILOT_DAILY_CAP`, `XFF_TRUSTED_HOPS`, `APP_NAME`, `PORT`, `RAG_SEMANTIC`, `STRUCTURED_LOGS`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD`, `PASSWORD_RESET_URL`, `POLICYNEST_SKIP_DOTENV`. Values are never documented.
