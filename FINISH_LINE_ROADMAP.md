# Finish-line roadmap

## Immediate fixes

1. **Make the evaluation reproducible.** Done when a clean checkout declares all Node dependencies, `run_eval.js` completes all 600 cases, output records the current engine hash, and line-by-line predictions are compared to the checked-in baseline.
2. **Restore the Python verification toolchain.** Done when `check_pack.py`, proxy contract tests, build, and local T1–T10 run successfully and their outputs are saved truthfully.
3. **Address F-10 only after the baseline.** Done when the minimal engine change has its new hash, 600-case comparison, static pack, T1–T10, and rulebook rationale recorded.

## Challenge-critical deliverables

1. Run five applicant and two reviewer studies using codes only; publish results separately by language and report reviewer cases individually.
2. Complete 20 hand-decided cases with a team adoption/override record.
3. Have an independent human label 30–40 held-out constructed cases; freeze and hash labels before the engine sees them, then report separately.
4. Finish the executive deck only after its underlying measurements are traceable and clearly labelled as observed, simulated, or in-sample.

## Product validation

1. Benchmark approved synthetic phone photographs on Android and iOS, by document type and extraction field.
2. Obtain answers to discovery questions when a problem-owner meeting is possible; otherwise keep them NOT ASKED.
3. Verify deployed static-site hash parity and Copilot health/response path without exposing credentials.

## Gated work

Reviewer queue UI, redesigned console, A/M/R controls and deep links begin only after the user supplies reviewer-console references. Definition of done includes approval against those references and browser accessibility regression.

## Final release

Fresh browser ideal path, all T1–T10, both themes/mobile, privacy regressions, reproducible pinned evaluation, integration disclosures, and a clean tracked working tree. Deploy only with explicit authorisation.
