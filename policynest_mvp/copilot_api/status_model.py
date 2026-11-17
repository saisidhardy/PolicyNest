"""Single source of truth for PolicyNest application statuses.

Every status defines:
- internal_enum: Unique system key
- label_en, label_hi: Applicant-facing localized labels
- staff_label: Internal operations label
- description_en, description_hi: Human-readable explanations
- action_required: Boolean flag indicating if applicant action is pending
- allowed_transitions: Valid target statuses
- badge_color: Visual UI token ('blue', 'amber', 'green', 'red', 'purple', 'gray')
"""

STATUS_DEFINITIONS = {
    "DRAFT": {
        "internal_enum": "DRAFT",
        "label_en": "Draft",
        "label_hi": "प्रारूप",
        "staff_label": "Draft",
        "description_en": "Your application has been started and saved as a draft.",
        "description_hi": "आपका आवेदन शुरू हो गया है और प्रारूप के रूप में सहेजा गया है।",
        "action_required": True,
        "allowed_transitions": {"IN_PROGRESS", "SUBMITTED", "WITHDRAWN"},
        "badge_color": "gray",
    },
    "IN_PROGRESS": {
        "internal_enum": "IN_PROGRESS",
        "label_en": "In Progress",
        "label_hi": "प्रगति पर है",
        "staff_label": "Application In Progress",
        "description_en": "You are completing your details and uploading verification documents.",
        "description_hi": "आप अपने विवरण भर रहे हैं और सत्यापन दस्तावेज़ अपलोड कर रहे हैं।",
        "action_required": True,
        "allowed_transitions": {"DRAFT", "SUBMITTED", "WITHDRAWN"},
        "badge_color": "blue",
    },
    "SUBMITTED": {
        "internal_enum": "SUBMITTED",
        "label_en": "Submitted",
        "label_hi": "जमा कर दिया गया",
        "staff_label": "Submitted for Verification",
        "description_en": "Your application has been submitted and queued for verification.",
        "description_hi": "आपका आवेदन जमा कर दिया गया है और सत्यापन के लिए कतार में है।",
        "action_required": False,
        "allowed_transitions": {"IN_REVIEW", "NEEDS_MORE_INFO", "KYC_APPROVED", "REJECTED"},
        "badge_color": "blue",
    },
    "IN_REVIEW": {
        "internal_enum": "IN_REVIEW",
        "label_en": "Under Review",
        "label_hi": "समीक्षाधीन",
        "staff_label": "Reviewer Assigned / In Review",
        "description_en": "An operations reviewer is verifying your submitted documents.",
        "description_hi": "एक परिचालन समीक्षक आपके प्रस्तुत दस्तावेज़ों का सत्यापन कर रहा है।",
        "action_required": False,
        "allowed_transitions": {"NEEDS_MORE_INFO", "KYC_APPROVED", "REJECTED", "FRAUD_HOLD"},
        "badge_color": "amber",
    },
    "NEEDS_MORE_INFO": {
        "internal_enum": "NEEDS_MORE_INFO",
        "label_en": "Correction Required",
        "label_hi": "सुधार आवश्यक",
        "staff_label": "Corrections Requested",
        "description_en": "A reviewer has requested corrections on one or more documents.",
        "description_hi": "समीक्षक ने एक या अधिक दस्तावेज़ों में सुधार का अनुरोध किया है।",
        "action_required": True,
        "allowed_transitions": {"SUBMITTED", "IN_REVIEW", "WITHDRAWN"},
        "badge_color": "amber",
    },
    "KYC_APPROVED": {
        "internal_enum": "KYC_APPROVED",
        "label_en": "Documents Verified",
        "label_hi": "दस्तावेज़ सत्यापित",
        "staff_label": "KYC Approved",
        "description_en": "All documents and identity checks have been approved. You are ready for POSP training.",
        "description_hi": "सभी दस्तावेज़ और पहचान जांच स्वीकृत हो गए हैं। आप POSP प्रशिक्षण के लिए तैयार हैं।",
        "action_required": True,
        "allowed_transitions": {"TRAINING_IN_PROGRESS", "TRAINING_COMPLETE"},
        "badge_color": "green",
    },
    "TRAINING_IN_PROGRESS": {
        "internal_enum": "TRAINING_IN_PROGRESS",
        "label_en": "Training in Progress",
        "label_hi": "प्रशिक्षण प्रगति पर है",
        "staff_label": "15-Hour LMS In Progress",
        "description_en": "You are currently completing the mandatory 15-hour IRDAI POSP training.",
        "description_hi": "आप अनिवार्य 15 घंटे का IRDAI POSP प्रशिक्षण पूरा कर रहे हैं।",
        "action_required": True,
        "allowed_transitions": {"TRAINING_COMPLETE"},
        "badge_color": "blue",
    },
    "TRAINING_COMPLETE": {
        "internal_enum": "TRAINING_COMPLETE",
        "label_en": "Training Completed",
        "label_hi": "प्रशिक्षण पूरा हुआ",
        "staff_label": "Training 15h Completed",
        "description_en": "You have completed your 15 hours of training and are eligible to take the POSP exam.",
        "description_hi": "आपने 15 घंटे का प्रशिक्षण पूरा कर लिया है और POSP परीक्षा देने के पात्र हैं।",
        "action_required": True,
        "allowed_transitions": {"EXAM_ELIGIBLE", "EXAM_PASSED", "EXAM_FAILED"},
        "badge_color": "green",
    },
    "EXAM_ELIGIBLE": {
        "internal_enum": "EXAM_ELIGIBLE",
        "label_en": "Exam Ready",
        "label_hi": "परीक्षा के लिए तैयार",
        "staff_label": "Exam Eligible",
        "description_en": "Your exam slot is ready. Take your 50-question POSP certification examination.",
        "description_hi": "आपका परीक्षा स्लॉट तैयार है। अपनी 50 प्रश्नों की POSP प्रमाणन परीक्षा दें।",
        "action_required": True,
        "allowed_transitions": {"EXAM_PASSED", "EXAM_FAILED"},
        "badge_color": "purple",
    },
    "EXAM_PASSED": {
        "internal_enum": "EXAM_PASSED",
        "label_en": "Exam Passed",
        "label_hi": "परीक्षा उत्तीर्ण",
        "staff_label": "Exam Passed (Score >= 50%)",
        "description_en": "Congratulations! You passed the POSP certification examination. Certificate issuance in progress.",
        "description_hi": "बधाई हो! आपने POSP प्रमाणन परीक्षा उत्तीर्ण कर ली है। प्रमाणपत्र जारी करने की प्रक्रिया जारी है।",
        "action_required": False,
        "allowed_transitions": {"CERTIFIED"},
        "badge_color": "green",
    },
    "EXAM_FAILED": {
        "internal_enum": "EXAM_FAILED",
        "label_en": "Exam Retake Pending",
        "label_hi": "पुनः परीक्षा लंबित",
        "staff_label": "Exam Failed (Score < 50%)",
        "description_en": "You did not achieve the 50% passing threshold. You may retake the exam after the mandatory cooling period.",
        "description_hi": "आप 50% उत्तीर्ण सीमा प्राप्त नहीं कर सके। अनिवार्य प्रतीक्षा अवधि के बाद पुनः परीक्षा दे सकते हैं।",
        "action_required": True,
        "allowed_transitions": {"EXAM_ELIGIBLE", "EXAM_PASSED", "EXAM_FAILED"},
        "badge_color": "amber",
    },
    "CERTIFIED": {
        "internal_enum": "CERTIFIED",
        "label_en": "Certified POSP",
        "label_hi": "प्रमाणित POSP",
        "staff_label": "Certified POSP Agent",
        "description_en": "You are officially certified as an IRDAI-compliant POSP agent with PolicyNest.",
        "description_hi": "आप आधिकारिक तौर पर PolicyNest के साथ एक IRDAI-अनुपालन POSP एजेंट के रूप में प्रमाणित हैं।",
        "action_required": False,
        "allowed_transitions": {"SUSPENDED"},
        "badge_color": "green",
    },
    "REJECTED": {
        "internal_enum": "REJECTED",
        "label_en": "Application Rejected",
        "label_hi": "आवेदन अस्वीकृत",
        "staff_label": "Rejected by Reviewer",
        "description_en": "Your application could not be approved based on IRDAI eligibility guidelines.",
        "description_hi": "IRDAI पात्रता दिशानिर्देशों के आधार पर आपका आवेदन स्वीकृत नहीं किया जा सका।",
        "action_required": True,
        "allowed_transitions": {"APPEAL_SUBMITTED"},
        "badge_color": "red",
    },
    "APPEAL_SUBMITTED": {
        "internal_enum": "APPEAL_SUBMITTED",
        "label_en": "Appeal Submitted",
        "label_hi": "अपील प्रस्तुत की गई",
        "staff_label": "Under Senior Review (Appeal)",
        "description_en": "Your appeal has been received and is being reviewed by a senior underwriting officer.",
        "description_hi": "आपकी अपील प्राप्त हो गई है और एक वरिष्ठ अंडरराइटिंग अधिकारी द्वारा इसकी समीक्षा की जा रही है।",
        "action_required": False,
        "allowed_transitions": {"IN_REVIEW", "KYC_APPROVED", "REJECTED"},
        "badge_color": "purple",
    },
    "FRAUD_HOLD": {
        "internal_enum": "FRAUD_HOLD",
        "label_en": "Verification Hold",
        "label_hi": "सत्यापन रोक",
        "staff_label": "Fraud / Anomaly Hold",
        "description_en": "Your application is currently on hold pending specialist verification.",
        "description_hi": "विशेषज्ञ सत्यापन लंबित होने तक आपका आवेदन वर्तमान में रोक पर है।",
        "action_required": False,
        "allowed_transitions": {"IN_REVIEW", "REJECTED", "KYC_APPROVED"},
        "badge_color": "red",
    },
    "WITHDRAWN": {
        "internal_enum": "WITHDRAWN",
        "label_en": "Withdrawn",
        "label_hi": "वापस लिया गया",
        "staff_label": "Withdrawn by Applicant",
        "description_en": "This application was withdrawn.",
        "description_hi": "यह आवेदन वापस ले लिया गया था।",
        "action_required": False,
        "allowed_transitions": {"DRAFT"},
        "badge_color": "gray",
    },
}


def get_status_info(status_code, lang="en"):
    """Return localized status metadata dictionary."""
    clean_code = str(status_code or "DRAFT").upper()
    info = STATUS_DEFINITIONS.get(clean_code, STATUS_DEFINITIONS["DRAFT"])
    return {
        "internal_enum": info["internal_enum"],
        "label": info["label_hi"] if lang == "hi" else info["label_en"],
        "description": info["description_hi"] if lang == "hi" else info["description_en"],
        "action_required": info["action_required"],
        "badge_color": info["badge_color"],
        "staff_label": info["staff_label"],
    }


def validate_transition(current_status, target_status):
    """Validate if transition between application statuses is legally permitted."""
    current = str(current_status or "DRAFT").upper()
    target = str(target_status or "").upper()
    if current == target:
        return True
    current_def = STATUS_DEFINITIONS.get(current)
    if not current_def:
        return False
    return target in current_def["allowed_transitions"]
