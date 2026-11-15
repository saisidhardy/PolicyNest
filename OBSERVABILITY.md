# Technical observability

Technical measurements are separate from business events. Every JSON API response includes a random correlation ID and no-store/nosniff headers. SQLite stores route templates, status, elapsed milliseconds and timestamp; request bodies, arbitrary URLs, IP addresses and credentials are excluded. Retrieval and LLM spans have IDs linked to the parent request. Optional `STRUCTURED_LOGS=1` emits only request ID, route, status and duration as JSON.

`/api/health` exposes provider configuration and remaining daily budget. `/api/ready` checks signing configuration, database access and corpus presence. Provider configuration is not proof that an actual model request works. The local launcher disables paid model calls by default.

With explicit telemetry consent, the frontend uses the bundled standard Web Vitals collector for LCP, INP and CLS, plus navigation timings, error counts and processing latencies. No exception messages, stacks, element text, file names, OCR text or audio are transmitted. Upload/OCR timing currently covers the combined read-and-gate pipeline, not separately profiled internal Tesseract phases. Browser data is self-reported and may be unavailable depending on browser support or lifecycle delivery.

Admin/ops Account workspace shows endpoint counts/error counts/mean latency, HTTP statuses, latency distribution, browser samples and operational records. Technical data is retained for 30 days and pruned on writes. This is a lightweight single-service view, not a continuous external uptime monitor. It does not establish a historical availability percentage. Dependency failures trigger deterministic assistant fallback; the fallback mode is disclosed.
