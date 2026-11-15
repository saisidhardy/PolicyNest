# PolicyNest codebase audit

**Audit date:** 15 November 2026 (local workspace review)
**Repository state:** `main` at `47a4f6866f0fea36fe6f691d3bca33bdd69209da`; tracks `origin/main`.
**Working tree:** no tracked changes; untracked `.idea/` only (user/IDE metadata, not touched).

## Actual structure and execution paths

| Area | Actual implementation | Evidence / status |
|---|---|---|
| Applicant app | One self-contained HTML/CSS/vanilla-JS source: `policynest_mvp/PolicyNest.html` | Source inspected; generated `site/index.html` contains the same engine hash. |
| Build | `policynest_mvp/build_site.py` wraps the source, copies worker shims/WASM, builds applicant-safe `kb.json`, and refuses embedded API keys | Present; not freshly executed because no Python executable is available in this environment. |
| OCR/PDF | Browser-side Tesseract and pdf.js through same-origin `ocr-worker.js` / `pdf-worker.js`; field parsing and type gates live in the HTML | Real client-side path in code; real phone-photo performance remains unmeasured. |
| Decision engine | Pure block between `ENGINE:START`/`ENGINE:END`; extracted by `eval/run_eval.js` | Version shown in source: 3.4.0. Canonical SHA-256 now: `c206388747e8381e0ce21f7677cfb83594b51db9f6581b6aca3f1d1ed9824350`. |
| Persistence | Consent-gated `localStorage` key `pn-onboarding-v1`; `savedCopy()` removes raw text, images, reviewer/internal data and masks repeat-face internal code | F-11 privacy fix added in this audit: typed account persistence now retains only the final four digits. Fresh browser regression is pending. |
| Copilot | Separate standard-library Python HTTP proxy in `policynest_mvp/copilot_api/main.py`; server-side BM25 retrieval; Anthropic SDK | Source/contract tests present. No key value inspected. Live health/AI path not verified. |
| Simulated integrations | PAN, penny-drop, face match and registry are local simulated results | Explicitly labelled in implementation/docs; no production provider adapter found. |
| Deployment | Static Embarko app config in `policynest_mvp/site/embarko.json`, proxy config in `copilot_api/embarko.json` | Repository has no deploy automation or live parity proof from this audit. No deployment attempted. |

## Security and data handling

- The browser does not receive the Anthropic key; configuration names documented by source are `ANTHROPIC_API_KEY`, `COPILOT_MODEL`, `COPILOT_EFFORT`, `PORT`, `APP_NAME`, `COPILOT_GLOBAL_PER_MIN`, `COPILOT_DAILY_CAP`, and `XFF_TRUSTED_HOPS`. Values were not read.
- The proxy validates allowed origins, caps request body size, checks a constrained context schema, refuses ID-number content, rate-limits, caps daily use, does retrieval itself, and filters unsafe applicant-facing output.
- Raw OCR text, image URLs and thumbnails are removed from saved progress. Aadhaar parsing stores only last four digits. Reviewer notes/internal events are removed from saved state.
- Source includes applicant-safe rendering/saving controls for human-review findings. This needs a fresh browser regression before being called verified.

## Baseline checks performed

| Check | Result |
|---|---|
| Git branch / SHA / working tree | Recorded above. |
| Engine canonical hash | PASS; matches `tools/check_pack.py` pin and `eval/out/eval_results.json`. |
| Inline JavaScript syntax | PASS; one inline script parsed successfully with Node. |
| Source vs generated-site engine hash | PASS. |
| `node eval/run_eval.js policynest_mvp/PolicyNest.html 04_DATASETS eval/out` | PASS: all 600 predictions; accuracy 100%, 0 wrongful approvals, 11 human routes. The prediction CSV is unchanged from the tracked baseline; only run time and machine timing changed. |
| `tools/check_pack.py`, proxy unit tests, build, T1–T10 | NOT RUN: `python` is unavailable on PATH. |
| Live site and live Copilot | NOT VERIFIED; no deploy, credential, or production-data action taken. |

Historical artifacts report 600/600 in-sample and T1–T10 pass, but they are evidence from earlier runs, not a fresh result from this audit.

## Audit conclusion

The architecture matches the handoff record: a protected deterministic client engine, browser OCR, device-only consented persistence, a separate guarded Copilot proxy, and deliberately simulated external checks. The evaluation dependency is now explicitly recorded in `package.json`/`package-lock.json`, and the clean engine baseline has been rerun. Python commands still cannot run in this host. Human validation, held-out labels, production AI-key configuration, phone-photo testing, and gated reviewer-console design remain outstanding.
