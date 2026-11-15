# Assistant implementation and evidence

The existing Copilot remains integrated in PolicyNest.html. It retrieves the generated rulebook corpus locally for fallback and through the existing server BM25 implementation for model answers. Server-returned citations are now displayed, rather than client-guessed citations.

## Added controls

- Show next action opens the current onboarding screen, explains the current stage, focuses a relevant field/upload/action and temporarily outlines it using the brand token. Reduced-motion preference is respected.
- Read guidance reads the latest assistant answer or current next action through the existing speech synthesis helper. Stop cancels playback and recognition. English/Hindi voice selection is available; it does not translate English source text.
- Voice input is hidden without recognition support. Clicking starts recognition/permission flow; recognised text goes into the question field for review before sending. Error text provides a typed fallback. No audio is stored by the application. The browser recognition provider may process audio externally according to browser settings.
- Ask a human reviewer requires a signed-in account, shows a confirmation form, and creates an appeal only on explicit submission. The reference is displayed only after HTTP success. Assignment to an authorised reviewer remains a separate admin operation.

## Executed verification

- `node tools/test_assistant.mjs`: PASS for next-action focus, signed-out appeal gate, deterministic fallback and no page JavaScript errors in a headless installed browser.
- Backend suite: 27 tests passed, including appeal ownership/assignment/resolution checks.
- Static pack/build: ALL PASS. Engine fingerprint unchanged.

## Remaining work and limits

The uploaded operational manual is ingested but not yet connected to retrieval. Embedding/vector retrieval is absent. The Copilot currently uses minimised browser state, not a server-authoritative authenticated application record. Signing in does not upload or associate the local demo application, so an appeal currently attaches to the account case but does not carry the local document evidence. Reviewer appeal UI and applicant status polling remain pending. Real microphone/audio output and Hindi voice availability require device testing. Actual model execution requires configured provider credentials and was not exercised in these tests. These limitations prevent claiming the complete assigned assistant/RAG capability is finished.
