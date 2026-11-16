---
status: proposed (AI-answered — needs human confirmation; GRILL_LOG G-14)
---
# External checks stay simulated; keyless lookups are deferred

PAN verification, the penny-drop holder name, face match and the IRDAI registry stay simulated and are labelled as simulated. No public lookup is added to the MVP: not Razorpay IFSC, not a pincode service, not a phone-number library. The integrations research found that every KYC vendor needs a server-side secret, that no public POSP registry API exists, and that DigiLocker needs partner onboarding. The keyless lookups would work under the CSP, but they call third parties, which the user's "no calls to government or bank services" decision rules out, and they add little to the demo (RF-70, RF-71, CX-05).
