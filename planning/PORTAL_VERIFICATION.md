# Applicant portal: verification report (P7, Opus verifier)

16 Nov 2026. Scope: commits `c63cd8f` (PORTAL_PLAN) to `d3cd12d` (Gemini assistant), checked against the brief's acceptance criteria (W), the deliverables (Y) and `planning/PORTAL_PLAN.md`. The verifier changed no source files. Screenshots are in `planning/screenshots/verify/`. All data was synthetic, and every server started for this run was stopped at the end.

## Verdict

**Pass with findings. No blockers.** Every W criterion passes on the production build, both locally and in the automated suites. There are **4 major** and **9 minor** findings. Most of the majors are in the AI assistant: on the main signed-in path its answers about the applicant's own state are wrong, its citations are thin, and its server fallback text is poor. Fix the majors before the production deploy. The engine is untouched (hash `c206388747e8381e`), and T1–T10 pass on the demo build.

## Acceptance table (W)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| W1 | Application reference visible | Pass | `PN-YYYY-NNNNN` shows after sign-up and copies; the same reference shows on a second device (`applicant_dash_390x844.png`, `second_device_after_login.png`). In focus mode it is hidden on the details and documents pages (minor m5). |
| W2 | Plain-language status | Pass | Status chips "Draft" / "Not started", and "Where you are now: You are filling in your details". |
| W3 | One dominant next action | Pass | The dashboard has exactly one `.btn.pri` ("Go to this step") at 1440, 768, 412, 390 and 360. |
| W4 | Exact resume position | Pass | "Step 1 of 6 · Your details · Page 3 of 4: How we reach you". The resume card reads "You stopped at: Your details, page 2 of 4". e2e: re-entry routes to the exact page. |
| W5 | Last-saved state | Pass | "Saved to your account, 16 Nov, 08:55". The offline state "Offline changes pending" saves again after reconnecting (`applicant_offline_pending.png`). Hidden in focus mode (m5). |
| W6 | Understandable journey | Pass | The six-stage journey (Details … Certificate) shows on the dashboard and the landing page. |
| W7 | Document progress distinct from form progress | Pass | "Details form: n of 4 pages complete" and "1 of 6 verified" are shown separately. |
| W8 | Recent notifications | Pass | Bell with an unread count, an "Updates" box on the dashboard, and the `#notifications` centre. |
| W9 | Obvious account access | Pass | Avatar menu, reachable and usable from the keyboard (Enter opens it, arrow keys move, Escape returns focus). Profile edits are saved on the server. |
| W10 | Language switch | Pass | EN↔HI on the landing page and in the app sets `<html lang>`. The Hindi CTAs are translated. |
| W11 | Staff features hidden from applicants | Pass | No staff links in the applicant navigation. A direct `#review`, `#evaluation` or `#audit` shows "You do not have access". `/api/reviewer/queue`, `/api/reviewer/case`, `/api/reviewer/decide`, `/api/admin/assign` and `/api/reports` all return 403 for an applicant. |
| W12 | No multi-row navigation on narrow screens | Pass | At 360, 390 and 412 the bottom navigation is one row of 5 items, 61 px high, with targets of 44 px or more. |
| W13 | Copilot never covers controls | Pass, with minor m1/m2 | The launcher never covers the dashboard CTA or the bottom navigation, and at the end of the page nothing sits under it. In one state at 390/412 it can float over "Resume onboarding" or "Delete my saved progress" before scrolling (m2). The close button is 36 px (m1). |
| W14 | No production demo language | Pass | `check_prod_build.py` passes. No demo wording on the landing page or the applicant and staff screens. `?demo=1` on prod shows no demo controls. |
| W15 | Hosting badge never covers the app | Pass (simulated) | `badgeSync()` measures `embarko-badge` and reserves `--badge-h`. P6 tests passed with a simulated badge (`planning/screenshots/after/*-with-badge.png`). The real Embarko badge is not present locally; recheck on the live host. |
| W16 | Recognisably PolicyNest (orange/black bento, both themes) | Pass | `landing_1440_light_en.png`, `landing_1440_dark.png`, `applicant_dash_1440_dark.png`. |

**User request (landing page):** the landing page offers only **Sign in, Create account, Account recovery**, plus basic information: what PolicyNest is, how it works, what you need, and how data is protected. Its only other controls are a skip link, EN/हिंदी, the theme toggle and one "How document checks work" disclosure. It has no app chrome (no sidebar, top bar, Copilot or bottom navigation). All three CTAs are in the first viewport at 360, 390 and 412 px wide. A signed-in user who opens `#welcome` is sent to their home, and a signed-out deep link such as `#review` lands on the landing page. **Pass.**

## Commands and results

| Command | Result |
|---|---|
| `python policynest_mvp/build_site.py --mode prod` / `--mode demo` | Both built; engine hash matches `eval_results.json` |
| `python tools/check_pack.py` | **ALL PASS** (engine `c206388747e8381e`, JS syntax for both builds, banned phrases, build) |
| `python tools/check_prod_build.py` | ALL PASS |
| `node --test tools/test_model.mjs` | 21/21 pass |
| `node --test tools/test_explanations.mjs` | pass |
| `node --test tools/test_assistant.mjs`, `tools/test_integrated.mjs` | Could not run: `@playwright/test` is not installed, and `test_integrated` expects `.python-runtime/python.exe` (m8) |
| Backend suite (`tools/run_backend_tests.py` in a temporary venv built from `requirements.txt`) | 55/55 OK |
| `python tools/t1_t10.py http://127.0.0.1:9410` (site-demo) | **10/10** |
| `python tools/test_portal_e2e.py` | **64/64** ALL PASS |
| Verifier Playwright session: backend on 9420 (temporary DB, real `.env` Gemini key), prod site on 9421, failing-key backend on 9422, staff provisioned with `admin.py provision` | 107 checks, 100 passed, 7 failed. Triage: 4 became findings (M1/M2 assistant, m1, m2); 1 is by design (an admin gets 403 on the reviewer-only queue; see m3); 2 did not reproduce (see the note below) |
| Targeted rechecks (stage context, second device, staff application, dark theme) | Confirmed M1 and M4; second-device reference OK; dark-theme contrast OK |

**Assistant (live Gemini, `gemini-3.5-flash`), as a signed-in applicant with real server state, 12 questions:**

- **Model answers:** 10 of 12, all mode `ai_grounded` from `authenticated_saved_progress`.
- **Latency:** median 3.7 s, max 5.8 s.
- **ID numbers:** a question containing a full PAN got `400 id_number` before any model call.
- **Prompt injection:** got `safe_refusal`.
- **Outcome predictions:** none, in English or Hindi; it said "I cannot predict…" and "मैं यह पहले से नहीं बता सकता…".
- **Language:** Hindi questions were answered in Hindi.
- **Citations:** only **1 of 11** answers carried a citation (M2).
- **Fallbacks:**
  - When the proxy is down (503), the page answers from the bundled rulebook, with citations and a plain note.
  - When the provider fails, the server returns 200 in deterministic mode with no error text, but the content is poor (M3).
- **Key exposure:** the key appears in no request, header or response (170 API exchanges captured), and in no backend log, built page or tracked file (`git grep -F` returned nothing).
- **`eval/out/assistant_eval.json`:** 44/45 (B02 failed: "no source cited"); server-state cases 4/4. These cases use display-label stages ("Documents") and so do not exercise M1.

**Sensitive-data scan:**

- **Request bodies:** none carried a full PAN, a 12-digit number or the full account number. The one exception is the deliberate ID-refusal probe, which the server refused.
- **Responses:** none carried a full identifier, and no request carried images or OCR text.
- **DOM:** the `#dashboard`, `#notifications`, `#history` and `#account` views are clean on both devices.
- **Storage and logs:** localStorage is clean on both devices; backend logs hold no PAN, account or mobile number.
- **After sign-out:** localStorage holds no personal values.

**Layout:**

- **Horizontal scroll:** none at 360, 390, 412, 768 or 1440 px, at 200% zoom (640×450 CSS px on `#dashboard`, `#apply` and `#account`), or with CSS zoom 2.
- **Phone targets:** 44 px or more in the bottom navigation, header and dashboard.
- **Header height:** the phone top bar is under 12% of the viewport.
- **Contrast spot checks:** body text, buttons, chips and headings on the dashboard and landing page, in both themes, had a minimum of 7.41:1. One automated low reading on "Get started" (dark text on the orange gradient) was a measuring artefact; the screenshot confirms it.

**Keyboard:** the dashboard's tab order reaches the account menu, and every focused control showed a visible focus ring.

**Note:** the second-device checks "same reference after sign-in" and "sign in again restores the account" failed once in the long session because of timing around the "Load my progress" dialog. In the targeted recheck the reference showed right after sign-in, and e2e passes both. Earlier runs were also polluted by orphaned verifier backends that shared the port on Windows; they were killed and the session was rerun cleanly.

## Findings

### Blocker

None.

### Major

**M1. The assistant gives the wrong next step for signed-in applicants on the details and documents stages.**

- **Where:** `policynest_mvp/copilot_api/assistant.py` (`ctx_from_progress`, `next_step`, `NEXT_EN`/`NEXT_HI`).
- **What happens:** the server progress stores stage *keys* (`"details"`, `"documents"`; see `portal.clean_progress`). `next_step` and the guidance tables are keyed by display labels (`"Your details"`, `"Documents"`). The lookup misses and falls back to "Before you start". An applicant on details page 2 or 3, even with a verified PAN, was told "Read the checklist on your screen and press Begin". In the same panel, the client greeting correctly said "You are on 'How we reach you' (page 3 of 4)" (`copilot_open_390.png`). The `stage == "Documents"` branch, which names the next document to upload, can never fire for signed-in users. The eval does not catch this because its cases use labels.
- **Fix:** map keys to labels in `ctx_from_progress`:

  | Key | Label |
  |---|---|
  | `details` | Your details |
  | `documents` | Documents |
  | `verification` | Verification |
  | `training` | Training |
  | `exam` | Exam |
  | `certificate` | Certificate |

  Also pass `resume.page` through as `details_page` instead of setting it to `None`. Add server-state eval cases whose stage is a stored key.

**M2. Live AI answers rarely cite sources.**

- **Where:** `assistant.finalize` / prompt in `assistant.py`.
- **What happens:** 1 of 11 `ai_grounded` answers carried a source, while facts such as "pass mark 50%" and "15 hours of training" came back with no citation. `assistant_eval` B02 fails for the same reason. Without citations, the brief's grounding and traceability requirement is not met.
- **Fix:** whenever the retrieved evidence supports a rule-based fact, attach the top retrieved `cite`s, or require at least one `[n]` marker in the model output. Answers drawn only from state can be labelled "From your application".

**M3. The server's deterministic fallback returns irrelevant text with unfilled placeholders.**

- **Where:** `assistant.deterministic` (`copilot_api/assistant.py`), used when the provider fails or the **50-per-day cap** is reached.
- **What happens:** with a failing key, the question "How many hours of training do I need?" returned "Your progress: Documents… From the rulebook: Dear {applicant_name}, your {document_name} photo could not be verified because {specific_defect_reason}… {secure_reupload_link}". This path is realistic in production, since the daily cap is 50.
- **Fix:** exclude message-template passages (placeholders in `{…}`) from deterministic quoting. Prefer the intent answers the page already has (`intentAnswer`), or answer only from the top passage's plain sentences.

**M4. Staff accounts get the applicant shell, and the review console shows the staff member's own empty local application.**

- **Where:** `PolicyNest.html`: the top bar, sidebar identity, `envchip` and Copilot for the reviewer and admin roles.
- **What happens:**
  - A signed-in reviewer sees "Application reference PN-2026-53722 (not yet registered)", "Not started", "Not saved yet", "Documents are read on your device" and "Ask Copilot". The assistant is applicant-only and returns 403 for staff.
  - The Review console shows "New applicant … Complete steps 1 and 2 in the Application section" (`reviewer_review.png`). It is not bound to any server case.
  - The server correctly refuses to create an application for staff: `GET /api/applications/me` returns 403.
- **Fix:** when `roleOf()` is staff, hide the application reference, status, save state, applicant `envchip` and Copilot launcher, and show a staff header (role, sign-in state). Until the queue screens are built (they wait for the user's references), show "No case selected" in the console instead of the local applicant panel.

### Minor

- **m1.** The Copilot close button is 36×36 px on phones (`.cp header button`, line ~486), below the brief's 44 px rule. The open sheet also covers the bottom navigation, which is acceptable for a modal sheet with a focus trap. Fix: set it to 44×44 under `max-width:640px`.
- **m2.** At 390×844 and 412×915, the floating "Ask Copilot" can sit over "Resume onboarding" or "Delete my saved progress" on the resume card before scrolling, depending on how many banners are above. The bottom padding keeps everything reachable at the end of the page. Fix: add a bottom margin to the last action row of `stepResume`, or hide the launcher while the resume card's actions are in the lower 120 px.
- **m3.** An admin sees "Review console" in the navigation, but `GET /api/reviewer/queue` returns 403 for admins (`workflows.queue` allows reviewers only). Align `can()` and the navigation with the server: either let admins read the queue, or label the view for admins as an oversight view.
- **m4.** In the dark theme, the landing page's primary "Sign in" turns white like the two secondary CTAs and loses its dominance (`landing_1440_dark.png`). Keep it near-black or use the orange fill.
- **m5.** In focus mode (details and documents pages), the application reference and the save state are hidden; only "Save and exit" shows (`details_p2_for_assistant.png`). Show a compact "Saved · time" in the focus bar.
- **m6.** The resume card still shows "0 Sittings so far", left over from the removed timer. Drop it, or show "Last saved".
- **m7.** The theme ignores `prefers-color-scheme` on the first visit, which matches the user's decision of light by default. Noted for information only.
- **m8.** The legacy PR #1 tests `tools/test_assistant.mjs` and `tools/test_integrated.mjs` cannot run: they need `@playwright/test` from npm and a `.python-runtime/` folder. Either port them to Python Playwright like the others, or document the setup.
- **m9.** OCR of a synthetic PAN took about 126 s headless, mostly loading the CDN worker and language data. The photo-quality gate held a clean synthetic canvas, and "Use this photo anyway" was needed. Once accepted, the result was correct: "Verified, PAN XXXXXX234K, confidence 0.95" (`applicant_pan_uploaded.png`). Measure first-upload time on a real phone before launch.

## Manual QA checklist

**Applicant (phone 390×844 and desktop, EN and HI):**

- [ ] The landing page shows only Sign in / Create account / Account recovery plus the about, how-it-works, what-you-need and privacy sections; the CTAs are visible without scrolling.
- [ ] Create an account (with the optional sync box ticked). You land on the dashboard with a `PN-` reference, the "Draft" status and one CTA.
- [ ] Copy the reference; the confirmation toast or announcement appears.
- [ ] Fill details pages 1–4. "Saving…" then "Saved" appears; Back and Next keep the values.
- [ ] Turn on airplane mode, edit a field: "Offline changes pending". Reconnect: "Saved".
- [ ] Upload a real PAN photo: instant feedback, the masked PAN (`XXXXXX…`), and a refusal for the wrong document in the wrong slot.
- [ ] Ask the Copilot "What should I do next?" on details and on documents. The answer must match the dashboard's next step (M1).
- [ ] Sign in on a second device: the same reference, the "Load my progress" offer, the resume position, and PAN, account and mobile asked again.
- [ ] Edit on both devices: the second save shows "newer progress was loaded", and nothing is lost.
- [ ] Check notifications and history; switch EN↔हिंदी (the whole page, including `html lang`); toggle the theme.
- [ ] Edit the profile name and mobile; the mobile shows masked.
- [ ] Sign out: back on the landing page, with no personal data in storage.
- [ ] With TalkBack or VoiceOver: the bottom navigation labels, the account menu, and the Copilot open/close with focus returning.
- [ ] Browser zoom at 200%: no sideways scrolling.

**Reviewer (provisioned with `admin.py provision --role reviewer`):**

- [ ] Signing in lands on `#review`; the navigation shows only Help and Review console.
- [ ] No applicant reference, status, save state or Copilot in the shell (M4).
- [ ] `#evaluation` and `#audit` show "You do not have access".
- [ ] A, M and R work on an assigned case once queue screens exist; until then, "No case selected".

**Admin (`--role admin`):**

- [ ] The navigation shows Review console, Evaluation and Audit trail, and each opens.
- [ ] The Review console for an admin either reads the queue or says what admins can do (m3).
- [ ] The Evaluation figures match `eval/out/` (no invented numbers).
- [ ] `admin.py assign --case <id> --reviewer <id>` is recorded, and the reviewer then sees the case.

**Release:**

- [ ] On the live host, open the dashboard at 360/390/412: the Embarko badge covers no navigation, Copilot or CTA (W15).
- [ ] `/api/health` reports `llm:true` and `daily_left`; the Gemini key is only in the app's env vars.
- [ ] Run `python tools/t1_t10.py` against the live demo site after the deploy.
