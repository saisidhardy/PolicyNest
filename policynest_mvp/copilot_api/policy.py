"""Central Attribute-Based Access Control (ABAC) decision engine for PolicyNest.

Implements NIST SP 800-162 ABAC across all 11 enterprise platform roles:
1.  applicant             - Self-service onboarding, document uploads, training, exam, appeal.
2.  reviewer              - Review assigned cases, evaluate docs, request corrections, citations.
3.  senior_reviewer       - Escalated cases, decision overrides, appeal resolution, reassignments.
4.  operations            - Queue monitoring, SLA management, reviewer assignment, operational metrics.
5.  compliance_officer    - Regulatory audits, compliance oversight, immutable audit trail inspection.
6.  fraud_investigator    - Fraud-flagged cases, anomaly evidence review, placing/clearing holds.
7.  training_admin        - LMS module authoring, training version management, progress tracking.
8.  exam_admin            - Question bank management, exam configurations, incident reviews, retakes.
9.  certificate_admin     - Certificate issuance, verification records, template & signing key management.
10. tech_admin            - Staff provisioning, invitation, role management (NO document image snooping).
11. auditor               - Read-only audit evidence inspection (strictly zero mutation rights).
(plus service role for machine-to-machine integrations with explicit scopes).

Enforces:
- Strict ownership boundaries (applicants only access their own resources).
- Assignment boundaries (reviewers only access assigned cases).
- Zero vertical escalation (privilege boundaries strictly enforced).
- Zero horizontal escalation (user A cannot access user B).
- Data sensitivity labels ('applicant', 'reviewer_only', 'restricted_fraud', 'system').
"""
import logging

log = logging.getLogger("policynest.policy")

# All recognized platform roles
PLATFORM_ROLES = {
    "applicant",
    "reviewer",
    "senior_reviewer",
    "operations",
    "compliance_officer",
    "fraud_investigator",
    "training_admin",
    "exam_admin",
    "certificate_admin",
    "tech_admin",
    "auditor",
    "admin",  # legacy alias mapped to tech_admin/operations
    "service",
}

# Capability sets
APPLICANT_ACTIONS = {
    "application.read",
    "application.save",
    "progress.save",
    "appeal.create",
    "assistant.ask",
    "portal.read",
    "portal.write",
    "document.upload",
    "document.read",
    "notification.read",
    "notification.dismiss",
    "timeline.read",
    "training.read",
    "training.update",
    "exam.start",
    "exam.submit",
    "agreement.execute",
    "certificate.read",
    "correction.submit",
}

REVIEWER_ACTIONS = {
    "application.read",
    "review.decide",
    "review.note",
    "review.comment",
    "review.cite",
    "review.correction",
    "appeal.read",
    "appeal.resolve",
    "audit.read",
    "document.review",
}

SENIOR_REVIEWER_ACTIONS = REVIEWER_ACTIONS | {
    "review.escalation",
    "review.override",
    "assignment.update",
    "review.resolve_dispute",
}

OPERATIONS_ACTIONS = {
    "application.read",
    "queue.monitor",
    "queue.read",
    "sla.read",
    "sla.manage",
    "assignment.create",
    "assignment.update",
    "operations.exception",
    "operations.followup",
    "staff.read",
    "reports.read",
    "audit.read",
}

COMPLIANCE_ACTIONS = {
    "application.read",
    "compliance.audit",
    "compliance.read",
    "compliance.review_rules",
    "case.audit_history",
    "reports.compliance",
    "audit.read",
    "reports.read",
    "fraud.case_read",
    "fraud.evidence_read",
}

FRAUD_ACTIONS = {
    "application.read",
    "fraud.case_read",
    "fraud.evidence_read",
    "fraud.hold_manage",
    "fraud.escalate",
    "fraud.note_create",
    "fraud.decide",
    "fraud.evaluate",
    "fraud.blacklist_manage",
    "audit.read",
}

TRAINING_ADMIN_ACTIONS = {
    "training.module_manage",
    "training.content_manage",
    "training.progress_read",
    "training.account_resolve",
    "reports.read",
}

EXAM_ADMIN_ACTIONS = {
    "exam.question_manage",
    "exam.config_manage",
    "exam.incident_review",
    "exam.retake_manage",
    "reports.read",
}

CERTIFICATE_ADMIN_ACTIONS = {
    "certificate.issue",
    "certificate.revoke",
    "certificate.verify",
    "certificate.template_manage",
    "reports.read",
}

TECH_ADMIN_ACTIONS = {
    "staff.provision",
    "staff.invite",
    "staff.role_update",
    "staff.status_update",
    "staff.read",
    "assignment.create",
    "assignment.update",
    "integration.configure",
    "settings.manage",
    "system.health_read",
    "audit.read",
    "reports.read",
}

AUDITOR_ACTIONS = {
    "audit.read",
    "timeline.audit_read",
    "reports.read",
    "staff.read",
    "compliance.read",
}


def allows(actor, action, resource):
    """Return True only if the actor is authenticated and authorized to perform action on resource."""
    if not actor or not actor.get("id") or not isinstance(resource, dict):
        return False

    role = actor.get("role")
    owner = resource.get("applicant_id")
    assigned = resource.get("reviewer_id")
    status = resource.get("status")
    sensitivity = resource.get("sensitivity", "applicant")

    # 1. Applicant Role
    if role == "applicant":
        if action not in APPLICANT_ACTIONS or owner != actor["id"]:
            return False
        # Applicants can NEVER read reviewer-only, fraud-restricted, or system data
        if sensitivity in ("reviewer_only", "restricted_fraud", "system"):
            return False
        if action == "progress.save":
            return status == "KYC_APPROVED"
        if action == "application.save":
            return status in ("DRAFT", "NEEDS_MORE_INFO")
        return True

    # 2. Reviewer Role
    if role == "reviewer":
        if action not in REVIEWER_ACTIONS:
            return False
        if sensitivity in ("restricted_fraud", "system"):
            return False
        # Reviewer can only act on cases assigned to them
        return assigned == actor["id"]

    # 3. Senior Reviewer Role
    if role == "senior_reviewer":
        if action not in SENIOR_REVIEWER_ACTIONS:
            return False
        if sensitivity == "system":
            return False
        # Can act on assigned cases or escalated/appealed cases across the system
        if assigned == actor["id"]:
            return True
        return action in ("review.escalation", "review.override", "assignment.update",
                          "appeal.read", "appeal.resolve", "audit.read")

    # 4. Operations Role
    if role == "operations":
        if action not in OPERATIONS_ACTIONS:
            return False
        if sensitivity in ("restricted_fraud", "system"):
            return False
        return True

    # 5. Compliance Officer Role
    if role == "compliance_officer":
        if action not in COMPLIANCE_ACTIONS:
            return False
        if sensitivity == "system":
            return False
        return True

    # 6. Fraud Investigator Role
    if role == "fraud_investigator":
        if action not in FRAUD_ACTIONS:
            return False
        # Fraud investigators ARE permitted to read restricted_fraud data
        return sensitivity != "system"

    # 7. Training Administrator
    if role == "training_admin":
        return action in TRAINING_ADMIN_ACTIONS

    # 8. Examination Administrator
    if role == "exam_admin":
        return action in EXAM_ADMIN_ACTIONS

    # 9. Certificate Administrator
    if role == "certificate_admin":
        return action in CERTIFICATE_ADMIN_ACTIONS

    # 10. Technology Administrator & legacy 'admin'
    if role in ("tech_admin", "admin"):
        if action not in TECH_ADMIN_ACTIONS:
            return False
        # Strict Principle 5.1: Tech admin NEVER receives unrestricted applicant-document access
        if sensitivity in ("reviewer_only", "restricted_fraud"):
            return False
        return True

    # 11. Auditor (Strictly read-only)
    if role == "auditor":
        if action not in AUDITOR_ACTIONS:
            return False
        # Strictly forbid any mutations
        if any(action.endswith(m) for m in (".save", ".create", ".update", ".delete", ".decide", ".resolve", ".manage")):
            return False
        return sensitivity != "system"

    # Service (machine-to-machine integration)
    if role == "service":
        scopes = actor.get("scopes", [])
        return bool(scopes) and action in scopes and sensitivity != "reviewer_only"

    return False
