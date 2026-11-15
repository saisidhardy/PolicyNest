# PS-01 test-set evaluation

Engine: policy-engine 3.4.0 · rulebook v3.2 · OCR-read cross-checks · simulated external services · run 2026-11-13 19:30 UTC · 600 applications

**Re-run on 15 Nov 2026 (runner timestamp `2026-11-15T11:55:03.635Z`):** re-run on the engine block currently in this repository, with Node 22.17.0. Every figure and all 600 predictions are identical to the prior tracked baseline; only the run time and the timing figure differ. Results are pinned to the code they scored: `engine_sha256` in `eval/out/eval_results.json` is `c206388747e8381e0ce21f7677cfb83594b51db9f6581b6aca3f1d1ed9824350` (the block from `/* ENGINE:START` up to, not including, `/* ENGINE:END */`, LF line endings). It matches the current source and generated site's engine block. Live-site parity was not checked in this audit. Still in-sample.

## How it was measured

- The engine block is taken directly from `policynest_mvp/PolicyNest.html`, between `ENGINE:START` and `ENGINE:END`, and run in Node. It is the same code the website runs.
- Inputs:
  - OCR text and OCR confidence per document, from `documents.csv`.
  - Penny-drop name, IRDAI registry hit and face-match score, from the data pack.
  - Typed details (name, DOB, PAN, state, education), from `application_truth.csv`.
  - Application date, from `applications.csv` (`created_at`).
- Scored against `application_truth.final_decision`, not the reviewers' verdicts.
- Cases routed to a person are scored by the AI's recommendation:
  - a different-person name counts as REJECT;
  - any other Human-only item counts as NEEDS_MORE_INFO.
- Reproduce with:
  ```
  npm install
  node eval/run_eval.js policynest_mvp/PolicyNest.html 04_DATASETS eval/out
  python eval/extra.py
  python eval/embed.py
  ```

**Important:** the rules were refined after a first run on this same test set. The current figures are therefore in-sample. Each change follows a rulebook rule, not a particular application, but only a fresh labelled set can confirm them.

## Results

| Metric | First run (3.3.0) | Now | Target |
|---|---|---|---|
| Accuracy | 98.0% | 100.0% | ≥ 95% |
| REJECT precision | 88.9% | 100.0% | |
| REJECT recall | 93.3% | 100.0% | ≥ 98% |
| NEEDS_MORE_INFO precision | 98.8% | 100.0% | |
| NEEDS_MORE_INFO recall | 95.5% | 100.0% | |
| Wrongful approvals | 3 | 0 | 0 |
| Straight-through and correct | not recorded | 98.2% | ≥ 60% |
| Messages per returned application | not recorded | 1.0 (mean 1.31 items) | 1 |

Confusion matrix (rows are the truth, columns are the engine's decision):

| Truth | APPROVE | NEEDS_MORE_INFO | REJECT |
|---|---|---|---|
| APPROVE | 364 | 0 | 0 |
| NEEDS_MORE_INFO | 0 | 176 | 0 |
| REJECT | 0 | 0 | 60 |

- 11 applications go to a person. Their ground truth: {'REJECT': 11}.
- Engine time: about 0.04 ms per application, on text that has already been read.

## Changes after the first run (12 wrong decisions)

- §4.1: a document with OCR confidence below 0.75 is treated as a quality problem and its values are not used (fixed 8 cases where noisy text from a glare or blurry photo looked like a different person or a wrong date)
- §4.2: when the typed PAN equals the characters printed on the card, the O/0 and I/1 noise correction is not applied (fixed 2 invalid-format PANs that were being 'corrected' into valid ones)
- §2 Step 0: fixed eligibility rules are applied to the typed details when the document cannot settle them: declared education below Class 10, typed PAN format and holder type, typed DOB under 18 (fixed 2 rejections)

## Reasons found (ground-truth reason → engine reason code)

| Reason | Found |
|---|---|
| POOR_QUALITY | 110 / 110 |
| NAME_SPELLING | 34 / 37 |
| BANK_NAME_MISMATCH | 28 / 31 |
| DOB_MISMATCH | 27 / 29 |
| FACE_LOW | 22 / 22 |
| EDU_NOT_ELIGIBLE | 21 / 21 |
| ALREADY_REGISTERED | 14 / 14 |
| NAME_MISMATCH_HARD | 12 / 12 |
| PAN_FORMAT_INVALID | 7 / 7 |
| UNDERAGE | 6 / 6 |
| PAN_NOT_INDIVIDUAL | 2 / 2 |

- 170 of 176 NEEDS_MORE_INFO applications get every reason in the first message.
- In the other 6, a blurry document hides a second problem until a clearer copy arrives. Those would need a second message.

## Fairness (accuracy by group)

- **Gender:** M 423 (100.0%), F 177 (100.0%)
- **Name pattern:** EXACT 436 (100.0%), SPELLING 36 (100.0%), SWAP 36 (100.0%), MIDDLE_MISSING 29 (100.0%), INITIAL 28 (100.0%), MIDDLE_ADDED 23 (100.0%), DIFFERENT 12 (100.0%)
- **State:** Maharashtra 79 (100.0%), Uttar Pradesh 75 (100.0%), Madhya Pradesh 56 (100.0%), Gujarat 52 (100.0%), Rajasthan 47 (100.0%), Tamil Nadu 41 (100.0%), Bihar 40 (100.0%), Karnataka 39 (100.0%), Odisha 34 (100.0%), Haryana 31 (100.0%), Delhi 30 (100.0%), West Bengal 28 (100.0%), Punjab 27 (100.0%), Telangana 21 (100.0%)

No gap was found, but several groups are small.

## Comparison

The reviewers' own document verdicts, rolled up per application (any REJECT → REJECT, else any re-upload or needs-info → NEEDS_MORE_INFO), match the ground truth in 87.0% of applications. This roll-up is our construction; real reviewers may check age and the registry separately.

## Not measured

- **OCR accuracy on real phone photos:** the test set gives OCR text, not images.
- **Real reviewer minutes per application:** needs reviewers using the product. There is an estimate below.
- **How clear applicants find the messages (target ≥ 4/5):** needs five real users.

## Before/after simulation (directional, not a forecast)

Script: `python eval/simulate.py`. It uses the applications workbook (`applications.csv` with duplicates removed, and `stage_events.csv`).

| Days from start to certificate (1732 certified agents) | Median | P90 | Best quarter |
|---|---|---|---|
| Today | 8.4 | 13.0 | 6.6 |
| With the engine | 7.4 | 11.5 | 5.6 |
| With the engine, plus the training link sent at KYC | 6.1 | 10.3 | 4.5 |

**Assumptions**
- **With the engine:**
  - A clean file takes 10 minutes from upload to KYC. This is a ceiling; the engine decides in seconds.
  - A returned file keeps the applicant's own observed time to answer the first fix request, plus 10 minutes.
  - Later fix loops and all queue waits are removed, because one message asks for everything.
  - Training and the exam are unchanged.
- **Review zone:** median 23.8 h today, against 10 min with the engine.
- **Training link at KYC:** the gap from KYC to starting training is capped at 1 hour. This is an assumption.
- **Silence what-if:** if silence after a fix request fell from 27.3% to 10%, about 106 more agents would certify (+6.1%). This uses today's rate at which applicants who reply go on to certify (78.9%). Only a pilot can show whether one clear message gets silence down to 10%.
- **Reviewer minutes per application (estimate):** 0.38 min, against 20.7 min today. Only the 1.8% of cases routed to a person get a reviewer, at today's minutes each.
