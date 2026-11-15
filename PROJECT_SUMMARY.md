# PolicyNest: project summary

**Everything done so far, how it was checked, and what is left.** Written 15 Nov 2026.

PolicyNest is a fictional insurance broker in the Masters' Union Applied AI Challenge, problem **PS-01 "AI-First Onboarding"** (problem owner: InsuranceDekho). The product is an AI-first onboarding journey for POSP (Point of Sales Person) insurance agents:

- it reads the applicant's documents;
- it cross-checks them against the onboarding rulebook;
- it decides approve, needs more info, or reject, citing a rule for every reason;
- it asks for everything missing in one message;
- it routes judgement calls to a person.

All data is synthetic.

| | |
|---|---|
| **Live app** | https://policynest.embarko.app (add `?demo=1` to open the Demo controls) |
| **Copilot proxy** | https://policynest-copilot.embarko.app (AI answers are off until an API key is added) |
| **Product spec** | [`PRD.md`](PRD.md) (requirements FR-01 to FR-73), [`PRODUCT.md`](PRODUCT.md) (goal statuses) |
| **Build record** | [`BUILD_LOG.md`](BUILD_LOG.md), [`planning/MASTER_AUDIT.md`](planning/MASTER_AUDIT.md) |
| **For a new session** | [`CLAUDE.md`](CLAUDE.md) |

---

## 1. Where it stands

- **Built and live:** the full applicant journey, the decision engine, the follow-up and re-check, reviewer routing, the audit trail, the Evaluation page, the Copilot (rulebook answers), accessibility, privacy hardening and the 13 features added from the external feature log.
- **Measured (in-sample):**
  - 600 of 600 test applications decided correctly (100.0%). The first run scored 98.0%.
  - REJECT recall 100.0%; no wrongful approvals; 98.2% straight-through.
  - All in-sample, because the rules were refined on the same 600 cases. Only a held-out set can confirm them.
- **Checked live:** the live engine hash equals the evaluated one (`c2063887…`), and all ten brief scenarios T1–T10 pass on the live site (`tools/t1_t10.py`).
- **Live:** a demo role switch ("View as" Applicant, Reviewer, Ops and compliance, or All views), labelled "not a login" (`2365af4`, deployed 15 Nov; checked live).
- **Left:** mostly work that needs people: usability tests, held-out labels, the AI key and the deck. See section 7.

## 2. Architecture

```
Browser (the whole app: policynest_mvp/PolicyNest.html, one file, vanilla JS)
 ├─ On-device OCR: Tesseract.js (images), pdf.js (PDF text) → per-slot document-type gate
 ├─ Photo check before OCR (blur, glare, dark, small), EXIF upright, downscale
 ├─ Rule engine (pure functions between ENGINE:START/END; SHA-256 pinned)
 │    PAN card = anchor · rulebook v3.2 name tiers · ~25 checks · APPROVE / NEEDS_MORE_INFO / REJECT / HUMAN_REVIEW
 ├─ Follow-up (one message, English/Hindi), re-check of changed documents only, rounds
 ├─ Reviewer console (Human-only items, evidence side by side), Audit trail, Evaluation page
 ├─ Saved progress: localStorage, only with consent, minimised copy (no images, no OCR text, no other person's data)
 └─ Copilot client: rule-based nudges + rulebook answers offline ──► Copilot proxy (Python, Embarko server app)
                                                                     holds the API key, retrieves passages itself,
                                                                     filters output, rate limits, 50 AI answers/day
Offline tooling: eval/run_eval.js (scores the exact engine block on 600 cases) · tools/check_pack.py (static gate)
                 · tools/t1_t10.py (Playwright T1–T10 runner) · policynest_mvp/build_site.py (build + key check)
Hosting: Embarko static site + Embarko server app. Nothing calls government or bank services (all simulated, labelled).
```

The design decisions are recorded as ADRs in [`docs/adr/`](docs/adr/):

- 0001: the engine block is the scored code;
- 0002: the proxy owns the key and the retrieval;
- 0003: saved progress stays on the device and is minimised;
- 0004: focus exits are counted, not timed;
- 0005: the exam pass mark is 50%;
- 0006: source precedence;
- 0007: one HTML file built in owned regions;
- 0008: external checks stay simulated;
- 0009: the PAN card is the anchor.

## 3. Timeline

| When | What | Evidence |
|---|---|---|
| 13 Nov | First MVP: journey, OCR, engine, follow-up, reviewer routing, evaluation (98.0% then 100.0% in-sample), deploy | `eval/EVALUATION_REPORT.md` |
| 14 Nov | Look v3 (bento, both themes); focused 30-minute sitting; autosave with consent; Onboarding Copilot and proxy | `CLAUDE.md` |
| 14 Nov | **Phase 1–3 planning:** skill audits (web design guidelines, accessibility, KPI dashboards, usability testing) → plan → spec with an audit table → two grilling rounds (21 decisions) | `planning/PHASE1_AUDIT_AND_PLAN.md`, `planning/PHASE2_SPEC_AND_AUDIT.md` |
| 14–15 Nov | Findings reconciled (80 findings, 18 contradictions), grill log (46 decisions), PRD written and confirmed | `RECONCILED_FINDINGS.md`, `GRILL_LOG.md`, `PRD.md` |
| 15 Nov 00:44 | **Step 0:** git repository, Node, evaluation re-run and pinned to the engine hash | `f3e5dba`, `e3ed958` |
| 15 Nov 00:52 | **Pass 3:** Copilot proxy looks up passages itself; applicant-safe corpus | `4c87e19` |
| 15 Nov 01:06–01:57 | **Passes 1, 2 and the original list:** multi-agent build (lanes H1–H6, N1, N2, each followed by a Sonnet audit and fixes) | `c3ce809` … `96722e8` |
| 15 Nov 13:10–13:49 | Audit fixes; **Opus master audit** (1 blocker, 3 major, 10 minor); corrections; docs | `b581609` … `e0f3e2b` |
| 15 Nov 14:09 | **Deployed** with the user's OK; live check passed | `0995f81` |
| 15 Nov 15:13–16:25 | **Feature triage** of an external implementation log → 13 features built in 5 audited lanes → **deployed**, T1–T10 10/10 live | `667482c` … `d8d285f` |
| 15 Nov | Demo role switch: built, audited, deployed with the user's OK; live hash match, T1–T10 10/10 live, roles checked live | `2365af4` |

## 4. How it was built and checked

- **Multi-agent build** (the user's design):
  - Haiku **builder** agents wrote each lane, with only one agent editing `PolicyNest.html` at a time.
  - Haiku **runtime workers** tested the paths a builder had not tested, in headless Chrome.
  - A Sonnet **auditor** reviewed every lane against the PRD's acceptance criteria; every lane came back "pass with fixes", and the fixes were applied.
  - An **Opus master audit** reviewed the whole build end to end, and its corrections were applied.
- **Gates after every change:**
  - `python tools/check_pack.py`: the engine hash is unchanged, JS syntax is valid, no banned phrases, the build passes.
  - A browser check of the change.
  - `python tools/t1_t10.py`: the brief's acceptance scenarios.
- **Engine safety:** the engine block's SHA-256 is pinned. It changed once on purpose (`75b9f3b`, a wording fix); the evaluation was re-run, all 600 predictions were byte-identical, and the hash was re-pinned.
- **Privacy tests:** a canary reviewer note and the other person's name in T4 were searched for on applicant screens and in the saved copy, before and after a reload. Neither was found.
- **Honesty rules:** no invented numbers; figures are labelled in-sample, simulated, estimate or directional; simulated services (PAN, penny drop, face match, IRDAI registry) are labelled.

## 5. What is built (by area)

**Applicant journey**

- **Start:** a first-visit checklist (the six documents, what gets one refused, what is saved and for how long, the language split, a shared-device line). The form starts empty and both consent boxes start unticked; Demo controls open with `?demo=1`.
- **The 30-minute sitting** (details and documents): full screen is optional, the timer can be hidden or turned off, there are warnings at 10 and 2 minutes, Extend adds 10 minutes any number of times, and leaving the screen never wipes anything. Phones get no full screen and no exit warnings.
- **Six document slots:**
  - each slot accepts only its own document type, with real on-device OCR and instant feedback;
  - a photo check runs before reading, with "Retake photo" or "Use anyway";
  - Take photo (camera) or Choose file;
  - the same file in two slots is refused;
  - each document keeps a version history;
  - "Good photo" hints show before the first upload.
- **Decision:**
  - approve, or one consolidated follow-up shown as a phone-style message (Copy, Open in WhatsApp, an SMS of 160 characters or fewer, Read aloud in Hindi or English);
  - a re-check runs only on the changed documents;
  - a rejection gives plain-language reasons plus Dispute, Start a new application, and Delete my saved progress.
- **Training (15 hours logged), exam (demo pass mark 50%), demonstration certificate:** the certificate can be printed or saved as PDF and carries an integrity seal with "Verify this certificate".
- **Accessibility:** near-black text on orange, visible focus everywhere, a skip link, one status region, links in the navigation, a compact phone bar, 24 px targets; both themes are clean at 375 px and at 1280 px (manual audit).
- **Offline IFSC helper:** format check plus the bank name from a bundled table; no lookups are sent anywhere.

**Decisions and people**

- **The rule engine:** the PAN card is the anchor; the rulebook name tiers; DOB, PAN format and holder type, age, Class 10 pass and board, bank-account ownership, face-match thresholds, the IRDAI registry. Every check cites its rule.
- **Human-only routing:**
  - a different person's name (never auto-rejected);
  - face match between 0.60 and 0.75;
  - a surname change;
  - an unlisted board;
  - disputes;
  - two selfie failures in a row (rulebook §4.6; internal fraud-desk referral, neutral message to the applicant).
- **Reviewer console:** the AI recommendation and the evidence side by side; a note is required to reject; an approval holds while the evidence is unchanged. The reviewer's note and the recommendation never reach the applicant or the saved copy.
- **Audit trail:** every decision with its rule, round, engine version and engine hash; internal events are marked and never saved; a "Rules applied" table.

**Evidence**

- **Evaluation page:**
  - the measured and running engine hashes, with "match";
  - accuracy, precision and recall, labelled in-sample;
  - the confusion matrix with the cases routed to a person;
  - fairness by state, gender and name pattern;
  - the 60.7% approved-first-time row;
  - the Stage 1 process map from the data pack;
  - the before/after simulation, labelled directional;
  - reviewer minutes, labelled as a simulated estimate.
- **Data for later:** the reviewer-queue seed and the ops KPI figures (`eval/out/queue_seed.json`, `kpis.json`); the held-out set procedure and templates (`eval/holdout/`).
- **Docs:**
  - discovery questions (13; all "not asked") in `planning/DISCOVERY_QUESTIONS.md`;
  - the usability test plan;
  - the Stage 1 pack (process map, 20 hand-decided cases, business case);
  - the feature triage (`planning/FEATURE_TRIAGE.md`).

## 6. Metrics (brief Table 7), with honest labels

| Metric | Target | Value | Label |
|---|---|---|---|
| Decision accuracy | ≥ 95% | 98.0% first run → 100.0% now | In-sample, 600 applications |
| REJECT recall | ≥ 98% | 93.3% first run → 100.0% | In-sample |
| Wrongful approvals | 0 | 3 first run → 0 | In-sample |
| Straight-through (no human touch, correct) | ≥ 60% | 98.2% (589/600) | In-sample |
| Approved first time, no follow-up | — | 60.7% (364/600) | In-sample |
| Follow-up rounds per returned application | 1 | 1.0 | In-sample (6 of 176 would need a second message) |
| Time to decision | < 10 min | Under 1 s on this demo | Measured on the device |
| Reviewer minutes per application | < 5 | 0.38 | Simulated estimate |
| Median days to certificate | baseline 8.4 | 7.4 (6.1 with the training link at approval) | Simulation, directional |
| Applicant clarity | ≥ 4/5 | Not measured | Needs the usability tests |
| Out-of-sample accuracy | — | Not measured | Needs the held-out labels |

## 7. What is left

**Needs you or your team** (PRD before-judging checklist)

| Item | Who | Notes |
|---|---|---|
| Usability tests: 5 applicants, 2 reviewers | You recruit and run; Claude prepares the sheets and analyses the results | Plan in `USABILITY_TEST_PLAN.md`; results in `planning/usability/results.csv` with participant codes only; clarity scored per language |
| Adopt or overrule the 20 hand-decided cases | A team member | `stage1/tables/part2_hand_decisions.csv`; adds a "team decision" column |
| Held-out labels (30–40 cases) | You label; Claude runs and reports | Procedure in `eval/holdout/README.md`: freeze with SHA-256 before any engine run; report separately as "held-out" |
| Copilot API key | You add `ANTHROPIC_API_KEY` to `policynest-copilot` in Embarko | Then one supervised round of answers checked against the guardrails |
| Executive deck (~10 slides) | Claude builds it after the usability results | Every number traced to a file; accuracy labelled in-sample |
| Discovery questions | You, with the problem owner | `planning/DISCOVERY_QUESTIONS.md` (13 questions) |

**Waiting for something**

- **Console redesign, queue screens, reviewer keys A/M/R:** wait for your reference designs. The queue data is already built.

**Optional**

- **Phone-photo bench:** print the image pack in `usability/image_pack/`, photograph it on two phones, and measure the type gate and field reading. If it is skipped, the deck says photo OCR was not tested.

**Known minor issues, left on purpose**

- **F-10:** an underage-reason path inside the engine can crash, but the screens cannot reach it. A fix needs an engine edit and a re-pin.
- **F-11:** saved progress keeps the full typed bank account number. This is FR-09, a nice-to-have.

**Not tested**

- Hindi screens (out of scope);
- iOS Safari;
- real phone cameras;
- the spoken "Read aloud" voice;
- real screen readers;
- an AI answer through the proxy (no key yet).

**Deliberately not built** (reasons in `planning/FEATURE_TRIAGE.md` §D and `PRD.md` §15):

- real government or bank API calls;
- DigiLocker;
- accounts and real authentication;
- a server-side store;
- the cross-application fraud graph;
- Hindi screens.

## 8. Repository map

| Path | What |
|---|---|
| `policynest_mvp/PolicyNest.html` | The whole app (source of truth) |
| `policynest_mvp/build_site.py`, `site/` | The build and the deployable folder |
| `policynest_mvp/copilot_api/` | The Copilot proxy (Python) |
| `eval/` | The evaluation runner, report, outputs, queue/KPI scripts, held-out procedure |
| `tools/check_pack.py`, `tools/t1_t10.py` | The static gate and the T1–T10 runner |
| `planning/` | Audits, spec, decisions, master audit, discovery questions, feature triage |
| `docs/adr/` | Architecture decision records |
| `stage1/` | The Stage 1 pack: process map, hand-decided cases, business case |
| `PRD.md`, `PRODUCT.md`, `BUILD_LOG.md`, `CLAUDE.md` | Spec, status, build record, session handoff |
| `01_…` to `08_…` | The PS-01 source package (brief, rulebook, synthetic datasets, specs) |

**Not in the repository:** `05_SPECIMEN_DOCUMENTS/sample_specimens/` (possibly real people's documents; never opened or committed), `.env`, and the Embarko deploy token.

## 9. How to run, test and deploy

```bash
python policynest_mvp/build_site.py                 # build site/
python -m http.server 8000 --directory policynest_mvp/site
python tools/check_pack.py                          # static gate
python tools/t1_t10.py http://localhost:8000        # T1–T10 (Playwright)
node eval/run_eval.js policynest_mvp/PolicyNest.html 04_DATASETS eval/out   # evaluation (needs papaparse)
```

Deploying uses the Embarko token stored on the developer's machine (see `CLAUDE.md` → Deployment). After every deploy, run `python tools/t1_t10.py https://policynest.embarko.app` and compare the live engine hash with `eval/out/eval_results.json`.
