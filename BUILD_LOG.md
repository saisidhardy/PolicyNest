# PolicyNest build log and hand-over

- **Last updated:** 15 Nov 2026, after passes 1 and 2 and the original list were built and audited. They were deployed the same day after the user's OK, and checked live.
- **What this file is:** the record of what was built against `PRD.md`, how each step was checked, what is live, and where to pick up. Read it with `PRD.md` → "Decisions confirmed by the user, 15 Nov 2026" (the plan), `GRILL_LOG.md` (the decisions) and `RECONCILED_FINDINGS.md` (the findings).
- **Status in one line:** step 0 and pass 3 are done, committed and live. Passes 1 and 2 and the original list are built, committed, audited, fixed and **live** (deployed 15 Nov after the user's OK; engine hash match and T1–T10 passed live).

## 1. Timeline

| When (15 Nov, IST) | Step | Commit | Deployed |
|---|---|---|---|
| — | Planning: reconciled findings, grill log, glossary, 9 ADRs, PRD (14 Nov); grill-me round with the user, 11 decisions confirmed (15 Nov) | in baseline | — |
| 00:44 | Git repository and baseline commit | `f3e5dba` | — |
| 00:48 | **Step 0:** Node, evaluation re-run, results pinned to the engine hash | `e3ed958` | — (no app change) |
| 00:52 | **Pass 3:** Copilot server does its own lookup; applicant-safe passages | `4c87e19` | Yes, with the user's go |
| after | Pass 3 deployed: proxy first, then site; live checks | — | Both live |
| 15 Nov, later | Passes 1 and 2 and the original list, built and audited (section 3b; commits `c3ce809` to `82aacd4`, docs `e0f3e2b`) | `c3ce809` … `e0f3e2b` | Yes, deployed after the user's OK; live check passed |

## 2. Step 0: foundation

**Done:**

- **Git repository** at the project root, branch `main`, no remote, commits under the user's own git identity.
  - `.gitignore` covers: `.env` and `.env.*` (`.env.example` is kept), `05_SPECIMEN_DOCUMENTS/sample_specimens/` (never opened, never committed), the autoresearch run's own inner repository (`autoresearch/*/workspace/`), `node_modules/`, `__pycache__/`, `.claude/settings.local.json`.
  - Checked before the first commit: none of those paths was staged.
- **Node.js 26.13.1 LTS** installed with `winget` (allowed by Phase 3 Q7).
  - The evaluation's one dependency (`papaparse@5.4.1`) is installed in the session scratch folder, **not** in the project, and found through `NODE_PATH`. To re-run elsewhere, run `npm i papaparse` in any folder and point `NODE_PATH` at its `node_modules`.
- **Evaluation re-run on today's engine:**
  - all figures **identical** to the 13 Nov run: accuracy 100.0%, REJECT and NEEDS_MORE_INFO precision and recall 1.0, 0 wrongful approvals, 11 routed to a person, straight-through 98.2%;
  - all **600 predictions identical line for line** (`eval_predictions.csv`); only the run time and the timing figure differ;
  - still **in-sample**.
- **Results pinned to the code** (ADR 0001, FR-57 runner side, FR-58):
  - `eval/run_eval.js` now writes `engine_sha256` into `eval/out/eval_results.json`;
  - the hash is SHA-256 of the block from `/* ENGINE:START` up to, not including, `/* ENGINE:END */`, with LF line endings;
  - value: **`c5da9cfb54f8e716b9630a7075a9f25db04e47cc696061ee7136e98019bce367`**;
  - it matches `policynest_mvp/PolicyNest.html`, `policynest_mvp/site/index.html` and the live site;
  - the `bd41…` value quoted on 14 Nov came from the same code with the end marker included: a different convention, not a code change.
- **Documents updated:** `eval/EVALUATION_REPORT.md` (re-run note), PRD, GRILL_LOG and RECONCILED_FINDINGS (canonical hash). RF-01 is marked resolved.

**Not done (optional in the plan):** region markers in `PolicyNest.html`. Under the lighter plan (U5), the main session edits the file alone, so they are not needed yet.

## 3. Pass 3: Copilot server

Requirements covered: FR-46 (server side), FR-47, FR-48, FR-49 (server side), FR-51, FR-65, FR-66. **`PolicyNest.html` was not changed.**

**Built:**

- **`policynest_mvp/build_site.py` (applicant-safe corpus):**
  - removes every sentence (in prose and lists) and every table row that contains fraud-desk wording (`fraud…`, `fake`, `forged`, `forgery`, `tamper…`, `suspicious`);
  - drops a passage left under 40 characters;
  - tags the rest `audience: "applicant"`;
  - refuses to build if any banned word is left.

  Result: 55 passages, 13 of which had internal wording removed, 0 fraud mentions. The useful rules stay. For example, rulebook §4.6 keeps "Ask for a fresh selfie in good light." and loses the fraud-desk sentence; §5 keeps every name rule except the "different person… flag to fraud desk" row; §7 loses only the fraud-desk SLA row. It writes the same file to `site/kb.json` (offline rulebook answers in the page) and `copilot_api/kb.json` (the server's lookup).
- **`policynest_mvp/copilot_api/main.py` (the Copilot server):**
  - **Retrieval:** its own BM25 over `kb.json`, using the same tokenising and scoring as the page. `passages` sent by a browser are **ignored**.
  - **Context schema:** keeps only the fields the page's `copilotContext()` sends, with types and lengths checked. Unknown fields are dropped; issue codes must look like codes.
  - **Inputs:** history trimmed to 6 turns of 800 characters. A question or user turn with a PAN-, Aadhaar- or account-shaped number gets `400 id_number`, **before any model call** (rulebook §4.3). An empty or non-object body gets `400`.
  - **Output:** an answer containing fraud wording or "you are approved/rejected" is replaced by a fixed safe sentence; a refusal returns a fixed sentence.
  - **Model:** Haiku models are called without the server-side fallback beta (Haiku 5.5 has none). Opus 5.5 at effort `low` is still the default.
  - **Kept unchanged:** origin allow-list without `null`, 24 KB body cap, 20 questions per 10 minutes per client, 30 per minute globally, 50 AI answers per UTC day, client address from the second `X-Forwarded-For` entry from the right.
  - **Response** now includes `sources` (the cites used). The page reads only `answer` and needs no change. On any non-200 reply the page gives rulebook answers.
- **`policynest_mvp/copilot_api/test_main.py`:** 14 contract tests, standard library only, model call stubbed (no key, no SDK). **All 14 pass.** They cover:
  - the corpus is applicant-safe;
  - browser passages are ignored;
  - the selfie question finds §4.6 with no fraud wording;
  - unknown context fields are dropped;
  - history is trimmed;
  - ID numbers are refused before a model call;
  - fraud wording and outcome predictions are replaced;
  - refusals give the fixed sentence;
  - `null` and unknown origins get 403;
  - bad bodies get 400;
  - a spoofed `X-Forwarded-For` does not reset the rate limit;
  - the daily cap;
  - health.

  Run: `python policynest_mvp/copilot_api/test_main.py`.
- **`CLAUDE.md`:** the proxy's new behaviour, the corpus rule, the tests and the deploy excludes are recorded under Deployment.

**Checked before deploying:**

- Retrieval spot-checks in Python on the shipped file: "my name is different on my marksheet" → Rulebook §9, §5, §4.4; "selfie failed twice" → §4.6, Rework spec §2.5, §3; "different person name" → §9, §5, Name-matching §2. None contains fraud wording.
- `site/kb.json` and `copilot_api/kb.json` are byte-identical.
- **A check in the browser pane could not run:** the pane was hidden and stuck on a site-permission check, so the Python check above stood in for it.

**Deployed (user's go, 15 Nov):**

1. **Proxy** `policynest-copilot`. The package held only `embarko.json`, `kb.json`, `main.py`, `requirements.txt` (no `.env`, caches or tests). Build status: live.
2. **Site** `policynest`: `site/` as built (index unchanged, new `kb.json`). Status: live.

**Live checks after deploy:**

| Check | Result |
|---|---|
| `GET /api/health` on the proxy | `{"ok": true, "llm": false, "model": "claude-opus-5-5", "daily_left": 50, "daily_cap": 50, "xff_hops": 2}` |
| `POST /api/copilot` with `Origin: null` | `403 origin_not_allowed` |
| `POST /api/copilot` from the live site's origin | `503 no_key` (expected: no key yet) |
| Live `kb.json` | 55 passages, all `applicant`, 0 fraud mentions, byte-identical to the local file |
| Live engine hash | matches `engine_sha256` in the evaluation results |

**Not checked live:**

- **An AI answer through the new lookup.** No key is set, and the server refuses before reaching the lookup. This path is covered only by the local tests.
- **T1–T10 in a browser.** The pane was hidden; the app page is byte-for-byte unchanged, and its engine hash matches.

## 3b. 15 Nov: passes 1 and 2 and the original list (built and live (15 Nov))

Requirements covered: FR-01 to FR-03, FR-05 to FR-07, FR-16, FR-23, FR-27 and FR-38 (both AI-proposed, not yet confirmed), FR-31, FR-36, FR-37, FR-41 to FR-45, FR-55 to FR-59, FR-61 to FR-63, FR-69. FR-60 is the runner only (not executed). FR-68 is in progress. FR-64 and FR-70 to FR-73 are not built.

**Built, one row per lane.** "Sonnet audit" is the second-model review of each lane; the commits named there are its fixes.

| Lane | What it does | Commits | Sonnet audit |
|---|---|---|---|
| H1 accessibility | Near-black text on orange fills, darker ok and info tokens, upload focus ring, status region, skip link, h2 cards, nav links, control names, phone top bar, touch targets | `49e9b93`, `5916c98` | Pass with fixes, fixes in `5916c98` |
| H2 sitting | Hide timer, turn off limit, 10- and 2-minute warnings announced, native dialog (Escape keeps the sitting going), no seconds recorded, extend after expiry gives 10 minutes from now | `dc91864`, `4aad625` | Pass with fixes, fixes in `4aad625` |
| H3 start and trust | Empty form, Demo controls behind `?demo=1`, six-document checklist with saving and language lines, honest compliance ticks, reviewer note kept reviewer-only | `ff8bad9`, `75231da` | Pass with fixes, fixes in `75231da` |
| H4 honest applicant screens | No "verified" pop-up or tile for an unclear photo, unbacked time and success claims removed, time to decision measured | `1166166` | No separate fix commit |
| H5 evaluation and audit | Measured vs running engine hash with match state, build warning on mismatch, decision events carry the engine, UTF-8 embed, in-sample labels, routed-to-a-person counts, process map | `05a3b6e`, `53f2eb2` | Pass with fixes, fixes in `53f2eb2` |
| H6 §4.6 two-selfie rule | Two selfie scores below 0.60 in a row (new photos only; 0.60 or more resets) route the case to a reviewer with an internal referral; the applicant sees a neutral message | `96722e8`, `b581609` | Pass with fixes, fixes in `b581609` |
| N1 queue and KPI data, held-out procedure | Reviewer-queue seed (16 cases: 11 test-set, 5 constructed), ops KPI figures with a source each, held-out procedure and templates in `eval/holdout/` | `06e9630`, `f666f6b` | Pass with fixes, fixes in `f666f6b` |
| N2 discovery questions and docs | `planning/DISCOVERY_QUESTIONS.md` (13 questions, all "not asked"); unverified brief quote marked; stale usability-plan lines fixed | `c6040ed`, `9b382a8` | Pass with fixes, fixes in `9b382a8` |
| Engine wording (FR-27) | The IDENTITY_NOT_CONFIRMED reason points to the Dispute button instead of "reply to this message". The only engine edit. Evaluation re-run: all 600 predictions byte-identical | `75b9f3b` | Hash checked in the master audit |
| Static check pack | `tools/check_pack.py`: engine hash, JS syntax, banned phrases, build | `c3ce809` | — |
| Master-audit corrections | Applicant screens and the saved copy never hold another person's name, a name tier or the AI recommendation; the "all six" pop-up fires; the reject panel says who decided; F-01 to F-09 and F-12 fixed | `82aacd4` | Master audit, below |

**Master audit.** `planning/MASTER_AUDIT.md` (Opus, read-only) reviewed the range and found 1 blocker, 3 major and 10 minor findings. The corrections in `82aacd4` fix F-01 to F-09 and F-12. Still open:

- **F-10:** an unreachable engine path in the UNDERAGE reason. Fixing it needs an engine edit and a re-pin.
- **F-11:** the full typed account number is saved (FR-09, nice to have).

The doc findings F-04, F-13 and F-14 were fixed in the docs pass of 15 Nov (this file, `PRD.md`, `PRODUCT.md`, `CLAUDE.md`, `planning/DISCOVERY_QUESTIONS.md`).

**Browser check after `82aacd4`** (local preview, headless Chrome, `?demo=1`): T1 to T10 reach the brief's outcome. T4 applicant screen and saved copy hold no other name, before and after reload, and the review console keeps the evidence. The "all six documents are in!" pop-up fires. The reject panel names a person when a person decided. The two-selfie rule routes to a person with neutral applicant text and an internal referral. A reviewer's approval of that case stands.

**How the build was run:** Haiku builders worked one at a time on `PolicyNest.html`, with Haiku runtime workers. A Sonnet auditor reviewed each lane. An Opus master audit then reviewed the range (read-only), and the corrections followed (`82aacd4`).

**Deployed 15 Nov** after the user's OK (deployed 15 Nov, Embarko deployment cmwhkvdrr00dq13bamf5bwc1q; live engine hash c2063887 matches the evaluation; T1–T10 passed on the live site). Live check: the served page's engine slice hashes to `c2063887…`, equal to `eval/out/eval_results.json`; the Evaluation page shows "match"; T1–T10 run through the live page's own controls with `?demo=1` all reached the brief's outcome (T4 and T8 to a person; T5 two fixes in one message; T6 plain-language PAN reason; T9 approved; T10 re-checked only the replaced documents with both rounds in the audit trail); no other person's name on applicant screens; no console errors under the site's security policy.

**Open items:**

- **Deploy** passes 1 and 2 and the original list, with the user's OK, then a live check: T1 to T10 and the engine hash.
- **AI key:** the user adds `ANTHROPIC_API_KEY`, then one supervised round of questions checked against the guardrails.
- **Usability tests:** 5 applicants and 2 reviewers. Results with codes only.
- **Held-out labels:** made by the user independently and frozen. The evaluation is reported separately.
- **Hand-decided cases:** a team member adopts or overrules each of the 20 (FR-73).
- **Executive deck:** every number traced; accuracy "in-sample"; simulation "directional".
- **Phone-photo bench (FR-72, optional):** if skipped, the deck says OCR on phone photos was not tested.
- **Console redesign (FR-64):** waits for the user's review-console references. The queue screens and A/M/R keys come with it.
- **F-10 and F-11** (above).
- **Certificate fields (A8):** check time taken and the other fields on the live site.
- **Not re-run after the master audit:** `eval/run_eval.js`, `eval/queue.py` and `eval/kpis.py`.

## 3c. 15 Nov: features from the external implementation log (built, deployed, checked live)

- **Triage:** `planning/FEATURE_TRIAGE.md` sorts the log into 13 features to add, 18 PolicyNest already had, and the rest rejected with reasons (live government and bank APIs, synthetic DigiLocker documents, the fraud-ring graph, accounts, server infrastructure, the phonetic auto-pass names). The log's headline numbers were not imported.
- **Build:** one workflow ran four sequential lanes on `PolicyNest.html` (each a Haiku builder, then a Sonnet audit, then a Haiku fix and commit) and, in parallel, the runner tool. Commits: `880f2fb` (L1 capture and photo), `d2e5ac1` (L2 message and voice), `327048f` (L3 IFSC, scenarios, rules panel), `a654378` (L4 certificate), `172b323` (L5 `tools/t1_t10.py`). All five audits returned pass with fixes; the fixes are in those commits. The engine hash is unchanged (`c2063887…`).
- **Checked by the orchestrator in the browser:**
  - `tools/t1_t10.py` passed 10 of 10 locally.
  - C1: a small photo is held with Retake or Use anyway.
  - C3: the camera inputs are there.
  - C4: the duplicate file is refused with the Aadhaar side named.
  - C5: the version history reads v1 → v2.
  - C6: two Read aloud buttons.
  - C7: the preview says simulated, Copy works with a real click, the `wa.me` link has no number, the SMS is 124/160 characters, and the Hindi version works.
  - C8: SBIN gives State Bank of India.
  - C9: T5 sets the right variants.
  - C10: the seal is shown and matches on verify; Print is there.
  - C11: the rules table has 23 checks.
  - At 375 px in both themes, the documents and certificate screens have no contrast failures, no targets under 24 px and no sideways scroll.
- **Not checked:** the spoken voice itself (no audio in the test browser), and real phone cameras.
- **Deployed** after the user's OK (deployment `cmwhpsgz202ib13bal6lwopu8`). Live check: the engine hash matches the evaluation (`c2063887…`), all new features are present in the served page, `python tools/t1_t10.py https://policynest.embarko.app` passed 10/10, and the photo check, real OCR and the type gate ran with no console errors under the site's security policy.

## 3d. 15 Nov: demo role switch (built, deployed, checked live)

- **What it is:** "View as" Applicant, Reviewer, Ops and compliance, or All views. The default is Applicant; `?demo=1` gives All views. Each role sees only its views, and a hidden view opened by URL shows a notice with a one-click switch. It is labelled "Demo role switch, not a login". The role lives in `pn-role` (localStorage) and never enters the saved application.
- **How it was built:** a Haiku builder, then a Sonnet audit (one functional gap: Reviewer and Ops opening the plain URL landed on a notice; two focus and announcement gaps), then a Haiku fix. Commit `2365af4`; chip wording fix in `fee2ce0`.
- **Deployed** after the user's OK (deployment `cmwhvzhjs050t13bapo81uw75`). Live check:
  - the engine hash matches (`c2063887…`);
  - `tools/t1_t10.py` passed 10/10 on the live URL;
  - each role lands on its first view (Applicant → Dashboard, Reviewer → Review console, Ops → Evaluation);
  - an Applicant opening `#review` gets the notice;
  - no console errors.

## 4. What is live now

| Piece | State |
|---|---|
| Site `https://policynest.embarko.app` | 15 Nov build (passes 1 and 2 and the original list) with the applicant-safe `kb.json`; deployment `cmwhkvdrr00dq13bamf5bwc1q`; live check passed |
| Proxy `https://policynest-copilot.embarko.app` | Pass 3 build; **AI answers off (no key)** |
| Engine | 3.4.0. Live, source and evaluation: `c2063887…` (600 of 600 in-sample, same predictions as `c5da9cfb…`) |

## 5. Where to pick up

1. **User:** the deploy OK for passes 1 and 2 and the original list, then the live check (T1 to T10, engine hash). Nothing is deployed until then.
2. **User:** add `ANTHROPIC_API_KEY` in the `policynest-copilot` App setup tab at https://embarko.ai/app, and run one supervised round of real questions against the guardrails.
3. **Human work before judging:** usability tests (5 + 2), adoption of the 20 hand-decided cases, held-out labels, the deck (PRD checklist).
4. **Later:** the console redesign, when the references arrive; F-10 (engine edit and re-pin); F-11.

## 6. Open items and cautions

- **25 grill decisions are still AI-answered** (list in GRILL_LOG → "Still AI-answered").
- **Line endings:** git's `core.autocrlf` is on for this user, so it warns "LF will be replaced by CRLF". The engine hash normalises line endings, so this does not affect the evaluation check.
- **`PolicyNest.html` changed** in passes 1 and 2 and the original list (section 3b). The engine block changed once (`75b9f3b`, wording only). The evaluation was re-run and all 600 predictions are byte-identical. The engine hash is `c2063887…` in the source, the build and the evaluation. The live site still runs `c5da9cfb…`.
- **Second autoresearch skill** at `~/.claude/skills/autoresearch` is still installed (RF-78).
- **No remote** is configured; nothing was pushed.
