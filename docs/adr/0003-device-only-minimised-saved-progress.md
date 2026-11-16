---
status: proposed (AI-answered — needs human confirmation; GRILL_LOG G-03, G-26)
---
# Saved progress is device-only, consented and minimised

Progress is saved only on the applicant's own device, only after they tick a separate save consent, and only for the fields that resume or the engine actually read. No images, no raw OCR text and no internal events are saved, and the typed bank account is cut to its last four digits. There is no server-side store, so this demo does not claim the state machine's DROPPED_OUT event or the five-year KYC retention rule. We chose this over saving the whole state, which the first build did (RF-03), because DPDP minimisation applies on the device too and phones are often shared. We chose it over a server store because a static host has none and the product keeps no state on our side.
