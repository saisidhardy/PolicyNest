"""Central ABAC decisions for PolicyNest server resources.

Resources are plain dictionaries so handlers and tests cannot bypass the policy with UI state.
"""

APPLICANT_ACTIONS = {"application.read", "application.save", "progress.save", "appeal.create", "assistant.ask"}
REVIEWER_ACTIONS = {"application.read", "review.decide", "appeal.read", "appeal.resolve", "audit.read"}


def allows(actor, action, resource):
    """Return True only for an authenticated, authorised actor/resource/action combination."""
    if not actor or not actor.get("id") or not isinstance(resource, dict):
        return False
    role = actor.get("role")
    owner = resource.get("applicant_id")
    assigned = resource.get("reviewer_id")
    status = resource.get("status")
    sensitivity = resource.get("sensitivity", "applicant")
    if role == "applicant":
        if action not in APPLICANT_ACTIONS or owner != actor["id"] or sensitivity == "reviewer_only":
            return False
        if action=='progress.save':return status=='KYC_APPROVED'
        return action != "application.save" or status in ("DRAFT", "NEEDS_MORE_INFO")
    if role == "reviewer":
        if action not in REVIEWER_ACTIONS or sensitivity == "system":
            return False
        return assigned == actor["id"]
    if role == "service":
        return bool(actor.get("scopes")) and action in actor["scopes"] and sensitivity != "reviewer_only"
    return False
