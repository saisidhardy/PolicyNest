"""Central Deterministic Next-Action Resolver for PolicyNest.

Computes the single dominant primary action for an applicant at any stage of the journey.
Never delegates action determination to probabilistic AI models.
Zero guesswork: strictly evaluates deterministic application state, document verification flags,
training hours, exam attempts, and appeals.
"""

REQUIRED_DOCUMENTS = ["PAN", "AADHAAR_FRONT", "AADHAAR_BACK", "CLASS10", "BANK"]


def resolve_next_action(application, lang="en"):
    """Evaluate application state and resolve the primary next action."""
    status = str(application.get("status", "DRAFT")).upper()
    details = application.get("details") or {}
    progress = application.get("progress") or {}
    docs = progress.get("documents") or {}
    training = progress.get("training") or {}
    exam = progress.get("exam") or {}
    cert = progress.get("certificate") or {}

    # 1. Certified State
    if status == "CERTIFIED" or cert.get("code"):
        return {
            "label": "View & Download POSP Certificate",
            "label_hi": "POSP प्रमाण पत्र देखें और डाउनलोड करें",
            "description": "Your official POSP certificate has been issued and is available for download.",
            "description_hi": "आपका आधिकारिक POSP प्रमाण पत्र जारी कर दिया गया है और डाउनलोड के लिए उपलब्ध है।",
            "destination": "#certificate",
            "priority": "normal",
            "stage": "Certificate",
            "reason_code": "CERTIFICATE_READY",
        }

    # 2. Exam Passed (Pending Certificate Issuance)
    if status == "EXAM_PASSED" or (exam.get("passed") is True and not cert.get("code")):
        return {
            "label": "Certificate Issuance in Progress",
            "label_hi": "प्रमाणपत्र जारी करने की प्रक्रिया जारी है",
            "description": "You have passed the exam. Your IRDAI appointment certificate is being generated.",
            "description_hi": "आपने परीक्षा उत्तीर्ण कर ली है। आपका IRDAI नियुक्ति प्रमाण पत्र तैयार किया जा रहा है।",
            "destination": "#certificate",
            "priority": "normal",
            "stage": "Certificate",
            "reason_code": "ISSUANCE_PENDING",
        }

    # 3. Exam Failed / Retake
    if status == "EXAM_FAILED" or (exam.get("score") is not None and exam.get("passed") is False):
        retake_at = exam.get("retake_at", 0)
        # Check cooling period (in ms)
        now_ms = int(time_now_ms())
        if retake_at and retake_at > now_ms:
            remaining_hours = max(1, int((retake_at - now_ms) / 3600000))
            return {
                "label": f"Retake available in {remaining_hours} hours",
                "label_hi": f"{remaining_hours} घंटे में पुनः परीक्षा उपलब्ध",
                "description": "IRDAI guidelines require a mandatory cooling period before retaking the examination.",
                "description_hi": "IRDAI दिशानिर्देशों के तहत पुनः परीक्षा देने से पहले एक अनिवार्य प्रतीक्षा अवधि आवश्यक है।",
                "destination": "#exam",
                "priority": "normal",
                "stage": "Exam",
                "reason_code": "EXAM_COOLING_PERIOD",
            }
        return {
            "label": "Retake POSP Certification Exam",
            "label_hi": "POSP प्रमाणन परीक्षा पुनः दें",
            "description": "Review the training modules and re-attempt the 50-question certification exam.",
            "description_hi": "प्रशिक्षण मॉड्यूल की समीक्षा करें और 50 प्रश्नों की प्रमाणन परीक्षा का पुनः प्रयास करें।",
            "destination": "#exam",
            "priority": "action-required",
            "stage": "Exam",
            "reason_code": "RETAKE_ELIGIBLE",
        }

    # 4. Exam Ready (Training completed, 15 hours logged)
    if status in ("EXAM_ELIGIBLE", "TRAINING_COMPLETE") or training.get("hours", 0) >= 15:
        return {
            "label": "Take POSP Certification Exam",
            "label_hi": "POSP प्रमाणन परीक्षा दें",
            "description": "You have completed your 15 hours of training. Take the 50-question exam (50% passing threshold).",
            "description_hi": "आपने अपने 15 घंटे का प्रशिक्षण पूरा कर लिया है। 50 प्रश्नों की परीक्षा दें (50% उत्तीर्ण सीमा)।",
            "destination": "#exam",
            "priority": "action-required",
            "stage": "Exam",
            "reason_code": "EXAM_READY",
        }

    # 5. Training in Progress
    if status in ("KYC_APPROVED", "TRAINING_IN_PROGRESS", "VERIFIED"):
        hours = training.get("hours", 0)
        remaining = max(0, 15 - hours)
        return {
            "label": f"Continue 15h Training ({hours}/15 Hours)",
            "label_hi": f"15 घंटे का प्रशिक्षण जारी रखें ({hours}/15 घंटे)",
            "description": f"Complete {remaining} more hours of IRDAI POSP training to unlock the certification examination.",
            "description_hi": f"प्रमाणन परीक्षा अनलॉक करने के लिए {remaining} और घंटे का IRDAI POSP प्रशिक्षण पूरा करें।",
            "destination": "#training",
            "priority": "action-required",
            "stage": "Training",
            "reason_code": "TRAINING_INCOMPLETE",
        }

    # 6. Rejection / Appeals
    if status == "REJECTED":
        return {
            "label": "Submit an Underwriting Appeal",
            "label_hi": "अंडरराइटिंग अपील सबमिट करें",
            "description": "If you believe this rejection was made in error, submit an appeal with supporting justification.",
            "description_hi": "यदि आपको लगता है कि यह अस्वीकृति गलत थी, तो उचित विवरण के साथ एक अपील प्रस्तुत करें।",
            "destination": "#history",
            "priority": "action-required",
            "stage": "Documents",
            "reason_code": "APPEAL_AVAILABLE",
        }

    if status == "APPEAL_SUBMITTED":
        return {
            "label": "Appeal Under Senior Review",
            "label_hi": "अपील वरिष्ठ समीक्षाधीन है",
            "description": "Your appeal has been received and is being evaluated by a senior underwriting officer.",
            "description_hi": "आपकी अपील प्राप्त हो गई है और एक वरिष्ठ अंडरराइटिंग अधिकारी द्वारा इसकी समीक्षा की जा रही है।",
            "destination": "#history",
            "priority": "normal",
            "stage": "Documents",
            "reason_code": "APPEAL_PENDING",
        }

    # 7. Document Corrections Requested (NEEDS_MORE_INFO)
    if status == "NEEDS_MORE_INFO":
        issue_count = sum(len(v.get("issues", [])) for v in docs.values() if isinstance(v, dict))
        msg = f"Fix {issue_count} document issue{'s' if issue_count != 1 else ''}"
        msg_hi = f"{issue_count} दस्तावेज़ त्रुटि ठीक करें"
        return {
            "label": msg if issue_count > 0 else "Submit Requested Information",
            "label_hi": msg_hi if issue_count > 0 else "अनुरोधित जानकारी प्रस्तुत करें",
            "description": "Reviewer requested clear re-uploads or corrected entries. Update and resubmit.",
            "description_hi": "समीक्षक ने स्पष्ट पुनः अपलोड या संशोधित प्रविष्टियों का अनुरोध किया है। अपडेट करके फिर से सबमिट करें।",
            "destination": "#documents",
            "priority": "urgent",
            "stage": "Documents",
            "reason_code": "CORRECTIONS_REQUIRED",
        }

    # 8. Under Human Review or Submitted
    if status in ("IN_REVIEW", "SUBMITTED"):
        return {
            "label": "Verification in Progress",
            "label_hi": "सत्यापन प्रगति पर है",
            "description": "Your documents have been submitted. Our operations team is completing verification.",
            "description_hi": "आपके दस्तावेज़ जमा कर दिए गए हैं। हमारी परिचालन टीम सत्यापन पूरा कर रही है।",
            "destination": "#history",
            "priority": "normal",
            "stage": "Documents",
            "reason_code": "VERIFICATION_IN_PROGRESS",
        }

    # 9. Draft / In Progress Checks:
    # 9a. Check Basics details
    basics_missing = not (details.get("name") and details.get("dob") and details.get("state") and details.get("city"))
    if basics_missing:
        return {
            "label": "Complete Personal & Address Details",
            "label_hi": "व्यक्तिगत और पते का विवरण पूरा करें",
            "description": "Step 2 of 6: Provide your full name, date of birth, educational qualification, and address.",
            "description_hi": "चरण 2 का 6: अपना पूरा नाम, जन्म तिथि, शैक्षणिक योग्यता और पता प्रदान करें।",
            "destination": "#basics",
            "priority": "action-required",
            "stage": "Basics",
            "reason_code": "INCOMPLETE_BASICS",
        }

    # 9b. Check Missing Documents
    missing_docs = []
    for slot in REQUIRED_DOCUMENTS:
        doc_entry = docs.get(slot) or {}
        st = doc_entry.get("status", "not uploaded").lower()
        if st in ("not uploaded", "pending", "missing"):
            missing_docs.append(slot)

    if missing_docs:
        first_missing = missing_docs[0].replace("_", " ").title()
        return {
            "label": f"Upload {first_missing}",
            "label_hi": f"{first_missing} अपलोड करें",
            "description": f"{len(missing_docs)} required verification document{'s' if len(missing_docs) > 1 else ''} remaining.",
            "description_hi": f"{len(missing_docs)} आवश्यक सत्यापन दस्तावेज़ शेष हैं।",
            "destination": "#documents",
            "priority": "action-required",
            "stage": "Documents",
            "reason_code": "DOCUMENTS_MISSING",
        }

    # 9c. All Basics and Documents filled in draft -> Ready to submit
    return {
        "label": "Review & Submit Application",
        "label_hi": "आवेदन की समीक्षा करें और जमा करें",
        "description": "All required details and documents are ready. Submit your application for underwriting review.",
        "description_hi": "सभी आवश्यक विवरण और दस्तावेज़ तैयार हैं। अंडरराइटिंग समीक्षा के लिए अपना आवेदन जमा करें।",
        "destination": "#apply",
        "priority": "action-required",
        "stage": "Documents",
        "reason_code": "READY_TO_SUBMIT",
    }


def time_now_ms():
    import time
    return time.time() * 1000
