# Business event contract and metric definitions

Browser usage events require the separate unticked analytics consent and an authenticated account. No keystrokes, raw documents, OCR content, passwords, tokens, identity numbers, audio or reviewer notes are accepted. The backend selects fixed fields and drops extra metadata.

Schema: generated `event_id`, server timestamp, HMAC-pseudonymous subject (one account case), allowlisted event name, actor role, allowlisted stage, source (`demo`/`operational`), bounded optional duration and result. Allowed document/issue dimensions are fixed enums. Browser activity is labelled demo; non-system accounts cannot relabel it operational. Retention is 90 days, pruned on writes. The persistent legal/audit record is separate.

Events cover registration/login, onboarding/stages, submissions, document operations/corrections, OCR outcomes, verification, training/exam/certificate, assistant use/helpfulness, escalation, appeals and reviewer activity. Some events require that the applicant opts in before the action; missing historical consent produces missing data, not zero success.

| Metric | Numerator / denominator or interpretation |
|---|---|
| Registration-to-start | Distinct users with start / distinct users with registration in the selected window |
| Submission | Distinct submitting users / distinct starting users |
| Certification | Distinct certified users / distinct starting users |
| Rejection | Distinct rejected users / distinct submitting users |
| Corrections | Distinct correcting users / distinct submitting users |
| OCR success | Observed successful processing events / observed success+failure events; not independently measured field accuracy |
| Human escalation | Distinct escalated users / distinct submitting users |
| Appeal rate | Distinct appealing users / distinct starting users |
| Assistant helpfulness | Distinct users explicitly marking help / distinct questioning users; self-report, not inferred resolution |
| Review workload | Current assigned cases per reviewer, sourced from case records |
| Appeal time | Resolution timestamp minus creation for resolved rows; open cases have no resolution duration |

These are windowed event ratios, not cohort conversion estimates; dates can omit an earlier denominator event. A zero denominator renders as unmeasured. Filters use measured data only. Live event reports remain separate from the inherited 600-case challenge evaluation and simulation. No business uplift is claimed. Inactivity is not automatically interpreted as abandonment; measuring true drop-off requires a defined observation window and sufficient consented activity. The dashboard displays missing evidence rather than invented statistics.
