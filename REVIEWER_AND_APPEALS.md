# Reviewer cases and appeals

An applicant owns one persistent account case. Admin CLI/API assignment records the previous and next reviewer in `assignment_history` and appends an audit event. Reassignment immediately changes API authorisation. Reviewers retrieve only their assigned queue and case detail; applicants cannot invoke reviewer functions.

The applicant confirms a concern in the Copilot appeal dialog. The backend creates a random `AP-...` reference, OPEN status and timestamp, links the appeal to the authenticated case, and freezes any synced minimised document metadata as evidence. The UI acknowledges submission only after HTTP success. No original document upload or audio is attached to an appeal. Applicants can view their references, responses and statuses in Account workspace.

The reviewer workspace displays assigned cases, progress provenance, appeals, private notes and audit events using existing PolicyNest cards/forms. A reviewer can return MORE_INFO, RESOLVED or ESCALATED with an applicant-facing response. Responses containing ID numbers or prohibited sensitive wording are refused. A resolved appeal cannot be silently rewritten. Internal decision rationales are stored separately and never returned in applicant case/status routes.

Reviewer decisions require a rulebook clause and rationale. They are recorded as NEEDS_MORE_INFO, HUMAN_REVIEW, KYC_APPROVED or REJECTED. Submitting or resolving an appeal alone does not change the case decision. The original demonstration engine journey remains separate from these recorded human actions; account metadata does not become a verified KYC document.

The large reviewer-console redesign, keyboard shortcuts and deep-link design remain gated by reference designs. This increment adds a functional account workspace without replacing the inherited console.

Verification: automated unit/API ownership/assignment tests and an actual browser registration→sync→appeal→assignment→reviewer response→applicant status flow. No real reviewer usability observations are claimed.
