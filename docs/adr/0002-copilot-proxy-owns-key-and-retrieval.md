---
status: proposed (AI-answered — needs human confirmation; GRILL_LOG G-07, G-23, G-24, G-25)
---
# The Copilot proxy owns the key, the retrieval and the guardrails

The static site cannot hold secrets, so the Anthropic key lives only in a separate server app (`policynest-copilot`). That app also runs retrieval itself over applicant-safe passages. It accepts only a question, a fixed-schema context of codes and the recent turns, filters banned wording on the way out, and enforces a rate limit and a daily cap. We rejected the original design, where the browser sent its own passages and free-text context, because it let anyone use the key as a general model (RF-10) and let internal fraud-desk passages reach applicants (RF-11). The browser keeps a copy of the passages only for the offline "rulebook answers" mode.

## Consequences

- Changing the corpus means redeploying the proxy as well as the site.
- Passages sent by a client are ignored, not rejected, so an older page keeps working.
