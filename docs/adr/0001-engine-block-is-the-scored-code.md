---
status: proposed (AI-answered — needs human confirmation; GRILL_LOG G-08)
---
# The engine block is the scored code, pinned by its hash

All decision logic lives in one pure block of the single-file app, between the `ENGINE:START` and `ENGINE:END` markers, with no DOM access, so the evaluation runs the exact text the site runs. Because the file is edited for many other reasons, every evaluation run records the SHA-256 of that block, the Evaluation page shows it beside the running page's hash, and the build warns when they differ. An accuracy figure is quoted only for the hash it was measured on. We chose this over a separate engine module because the app must stay one self-contained file (ADR 0007), and because a hash makes "same code as the site" checkable rather than asserted (RECONCILED_FINDINGS RF-01).
