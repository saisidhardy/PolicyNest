# Gap and defect register

## Verified current issues

| ID | Severity | Impact / root cause | Component | Recommended fix and required test | Priority |
|---|---|---|---|---|---|
| G-01 | High | Evaluation could not run from this checkout because `eval/run_eval.js` required `papaparse` without a manifest. | `eval/run_eval.js` | RESOLVED in this audit: explicit minimal `package.json`/lock added; 600-case run completed with unchanged predictions. | P0 |
| G-02 | High | Required Python checks cannot run in this host because `python`/`py` are unavailable. This is environment blocking, not an application defect. | build/check/test commands | Use an approved Python interpreter or CI; run `check_pack`, proxy contracts, build and T1–T10. | P0 |
| G-03 | High | No fresh proof that generated/deployed site and current main match; live Copilot health/LLM path is unknown. | deployment / proxy | Read-only live parity and health check after local checks; do not configure keys/deploy without authority. | P0 |
| G-04 | Medium | `rejectReasons` uses `P.dob.split` for `UNDERAGE`; typed-DOB fallback can make this unreachable UI path throw if validation is bypassed/programmatically invoked. | protected engine | Do not change until G-01/G-02 baseline is restored; then make minimal fallback change and execute full engine-change protocol. | P1 |
| G-05 | Medium | Real phone-photo OCR/type-gate accuracy has not been measured. | OCR workflow | Run approved synthetic photo bench on Android and iOS; report measurements or explicitly disclose absence. | P2 |
| G-06 | Medium | Usability and held-out evaluation are intentionally incomplete and require independent human judgement. | `usability/`, `eval/holdout/` | Conduct, anonymise, freeze/hash labels before running; never fabricate. | P1 |

## Historical findings rechecked against current source

| ID | Finding | Current code reading | Status |
|---|---|---|---|
| F-10 | Typed-DOB `UNDERAGE` reason may dereference absent PAN DOB | Present at `rejectReasons`; still needs protected-engine workflow | OPEN (G-04) |
| F-11 | Full typed bank account in saved copy | Fixed in this audit: `savedCopy()` now writes `o.f.acct=o.f.acct.slice(-4)` | FIX CODED, NOT FRESHLY BROWSER-VERIFIED |
| F-01/F-02/F-03 | Review-data leak, toast count, reviewer rejection wording | Prior commit history and source indicate fixes; no fresh end-to-end run | FIX CODED, NOT FRESHLY VERIFIED |

## Enhancements / external blockers (not defects)

- Multi-case queue, reviewer redesign, A/M/R keyboard controls and deep links wait for user reference designs.
- PAN, penny drop, face match, registry, DigiLocker and messaging stay simulated unless credentials, partner approval and product authority are supplied.
- No applicant/reviewer participant data, held-out labels or OCR outcomes will be invented.
