# PolicyNest feature status matrix

Classifications distinguish code presence from current verification. “Historical” means a repository artifact reports it but this audit did not re-run it.

| Requirement area | Implementation location | Evidence | Test / live status | Classification / gap |
|---|---|---|---|---|
| First visit, consent, progressive six-step journey | `PolicyNest.html` state/render functions | Source and prior master audit | Historical browser checks; not fresh | BUILT BUT NOT VERIFIED |
| Six slots, camera/upload, type gate, feedback | `readDoc`, `classify`, `judge`, `addDoc` | Browser OCR/type-gate code | Historical T1–T10 + OCR canvas test; real phone photos not measured | PARTIALLY BUILT |
| Themes, sidebar, accessible focus | HTML/CSS and theme actions | Source | Syntax only this audit; accessibility/browser checks historical | BUILT BUT NOT VERIFIED |
| Saved progress / resume | `persist`, `savedCopy`, `restore` | Source removes images/raw OCR/internal data; bank account is last four only | Needs fresh storage regression | BUILT BUT NOT VERIFIED |
| Training, exam, certificate / print / seal | application render and certificate functions | Source, prior commits | Historical only | BUILT BUT NOT VERIFIED |
| OCR, PDF extraction, field confidence/evidence | workers plus parsing functions | Source | No device-photo benchmark | PARTIALLY BUILT |
| Versioning, duplicate/type refusal, incremental re-check | document versions, `changed`, `recheck` | Source and T10 runner | Historical T10; fresh runner blocked | BUILT BUT NOT VERIFIED |
| Aadhaar minimisation / identity matching | parser, `savedCopy`, engine | Source inspection | Need browser/privacy regression | BUILT BUT NOT VERIFIED |
| Rulebook decision engine / explanations / history | protected engine block, audit trail | Current hash matches pin | Fresh 600-case run blocked by missing `papaparse` | BUILT BUT NOT VERIFIED |
| Human-only routing and reviewer controls | review functions / review view | Source and historical T4/T8 | No multi-case queue screen; fresh browser test pending | PARTIALLY BUILT |
| Consolidated bilingual recovery / disputes | follow-up, fix, dispute functions | Source | Historical T3/T5/T7/T10 | BUILT BUT NOT VERIFIED |
| Copilot retrieval / fallback / proxy guardrails | `copilot_api/main.py`, `kb.json`, client cp functions | Source and contract suite | Unit tests and live health not fresh; key status unknown | BUILT BUT NOT VERIFIED |
| Evaluation dashboard, queue seed, KPI sourcing | `eval/*.py`, embedded results | Files present | Evaluation runner blocked locally | BUILT BUT NOT VERIFIED |
| Build / static checks / T1–T10 | `build_site.py`, `check_pack.py`, `t1_t10.py` | Tools present | Python unavailable; eval has undeclared Node dependency | PARTIALLY BUILT |
| Usability study | `USABILITY_TEST_PLAN.md`, templates/image pack | Plan and materials | No recorded participants/results | BLOCKED BY USER INPUT |
| Held-out labelled set | `eval/holdout/` templates/procedure | Templates only | Independent labels absent | BLOCKED BY USER INPUT |
| Real external verification / DigiLocker / messaging | simulated local helpers | Deliberately absent per PRD | Requires partner credentials/approval | BLOCKED BY EXTERNAL ACCESS |
| Multi-case reviewer queue/re-design/deep links | queue data exists; no authorised UI design | PRD and planning | Waits for references | BLOCKED BY USER INPUT |
