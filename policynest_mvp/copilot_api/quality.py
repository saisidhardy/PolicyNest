"""Document Quality Assessment and Guided Capture Engine.

Provides:
1. Deterministic quality scoring (resolution, aspect ratio, byte entropy, client optical signals).
2. Bilingual (English / Hindi) defect diagnosis and coaching.
3. Per-document-slot preparation guidelines.
"""
from typing import Dict, List, Optional, Tuple

QUALITY_PASS_THRESHOLD = 0.70

SLOT_GUIDELINES = {
    "PAN": {
        "en": {
            "title": "PAN Card Guidelines",
            "preparation": "Ensure all 4 corners of your PAN card are visible on a plain surface. Avoid overhead flash reflections across your name, PAN number, or date of birth.",
            "checklist": [
                "Full rectangular card visible",
                "PAN number is clearly readable",
                "Name and Date of Birth match application details",
                "Personal PAN (4th letter must be 'P')",
            ],
        },
        "hi": {
            "title": "पैन कार्ड दिशानिर्देश",
            "preparation": "सुनिश्चित करें कि आपके पैन कार्ड के चारों कोने एक सादे पृष्ठ पर स्पष्ट दिखाई दें। नाम, पैन नंबर और जन्म तिथि पर रोशनी की चमक (फ्लैश) से बचें।",
            "checklist": [
                "पूरा कार्ड दिखाई दे",
                "पैन नंबर साफ़ पढ़ने योग्य हो",
                "नाम और जन्म तिथि आवेदन से मेल खाते हों",
                "व्यक्तिगत पैन (चौथा अक्षर 'P' होना चाहिए)",
            ],
        },
    },
    "AADHAAR_FRONT": {
        "en": {
            "title": "Aadhaar Card Front",
            "preparation": "Capture the front of your Aadhaar card or e-Aadhaar sheet showing your photograph, full legal name, date of birth, and masked UID number.",
            "checklist": [
                "Clear photograph",
                "Date of birth and gender clearly visible",
                "Masked Aadhaar or last 4 digits visible",
            ],
        },
        "hi": {
            "title": "आधार कार्ड (सामने का भाग)",
            "preparation": "अपने आधार कार्ड या ई-आधार का सामने का भाग कैप्चर करें जिसमें आपकी तस्वीर, पूरा कानूनी नाम, जन्म तिथि और मास्क किया गया आधार नंबर दिखे।",
            "checklist": [
                "स्पष्ट तस्वीर",
                "जन्म तिथि और लिंग स्पष्ट दिखें",
                "मास्क किया गया आधार या अंतिम 4 अंक दिखें",
            ],
        },
    },
    "AADHAAR_BACK": {
        "en": {
            "title": "Aadhaar Card Back",
            "preparation": "Capture the back of your Aadhaar card showing your residential address, PIN code, and the QR code.",
            "checklist": [
                "Full address with PIN code visible",
                "QR code intact and unblurred",
            ],
        },
        "hi": {
            "title": "आधार कार्ड (पीछे का भाग)",
            "preparation": "अपने आधार कार्ड का पिछला हिस्सा कैप्चर करें जिसमें आपका आवासीय पता, पिन कोड और क्यूआर कोड दिखाई दे।",
            "checklist": [
                "पिन कोड सहित पूरा पता दिखे",
                "क्यूआर कोड बिना धुंधलेपन के साफ़ हो",
            ],
        },
    },
    "CLASS10": {
        "en": {
            "title": "10th Standard Certificate / Marksheet",
            "preparation": "Upload your secondary school passing certificate or marksheet issued by a recognized education board (CBSE, ICSE, State Board, or NIOS).",
            "checklist": [
                "Candidate name clearly legible",
                "Board name and roll number visible",
                "Date of birth and passing status indicated",
            ],
        },
        "hi": {
            "title": "10वीं कक्षा का प्रमाण पत्र / अंकतालिका",
            "preparation": "मान्यता प्राप्त शिक्षा बोर्ड (CBSE, ICSE, राज्य बोर्ड या NIOS) द्वारा जारी 10वीं उत्तीर्ण प्रमाण पत्र या अंकतालिका अपलोड करें।",
            "checklist": [
                "अभ्यर्थी का नाम स्पष्ट रूप से पढ़ने योग्य हो",
                "बोर्ड का नाम और रोल नंबर दिखाई दे",
                "जन्म तिथि और उत्तीर्ण स्थिति स्पष्ट हो",
            ],
        },
    },
    "BANK": {
        "en": {
            "title": "Bank Account Proof",
            "preparation": "Upload a cancelled cheque, bank passbook front page, or account statement with your name printed by the bank. Used strictly for authorized POSP commission payouts.",
            "checklist": [
                "Applicant's printed name visible",
                "Account number and IFSC code clearly legible",
                "Must be an individual account in applicant's name",
            ],
        },
        "hi": {
            "title": "बैंक खाता प्रमाण",
            "preparation": "रद्द किया गया चेक (Cancelled Cheque), बैंक पासबुक का पहला पन्ना या बैंक स्टेटमेंट अपलोड करें जिसमें आपका नाम बैंक द्वारा मुद्रित हो। यह केवल कमीशन भुगतान के लिए उपयोग होता है।",
            "checklist": [
                "आवेदक का मुद्रित नाम दिखना चाहिए",
                "खाता संख्या और IFSC कोड स्पष्ट होने चाहिए",
                "आवेदक के नाम पर व्यक्तिगत बचत/चालू खाता होना चाहिए",
            ],
        },
    },
    "SELFIE": {
        "en": {
            "title": "Live Verification Selfie",
            "preparation": "Position your face directly in the frame with even lighting. Remove sunglasses, hats, or face masks. Keep a neutral expression.",
            "checklist": [
                "Face centered and fully visible",
                "Good ambient lighting without strong backlighting",
                "Eyes open and looking directly at camera",
            ],
        },
        "hi": {
            "title": "लाइव सत्यापन सेल्फ़ी",
            "preparation": "पर्याप्त रोशनी में अपना चेहरा सीधे फ्रेम में रखें। धूप का चश्मा, टोपी या मास्क हटा दें। चेहरा सामान्य रखें।",
            "checklist": [
                "चेहरा केंद्र में और पूरी तरह दिखाई दे",
                "अच्छी रोशनी हो, पीछे से तेज़ रोशनी न हो",
                "आँखें खुली हों और सीधे कैमरे की ओर देखें",
            ],
        },
    },
}

DEFECT_COACHING = {
    "IMAGE_BLURRY": {
        "en": "The uploaded photo is too blurry to read critical details. Please hold your device steady, tap the screen to focus on the text, and capture again under steady light.",
        "hi": "अपलोड किया गया फ़ोटो बहुत धुंधला है और विवरण पढ़ा नहीं जा रहा है। कृपया डिवाइस को स्थिर रखें, स्क्रीन पर टैप करके फ़ोकस करें और अच्छी रोशनी में दोबारा कैप्चर करें।",
    },
    "IMAGE_GLARE": {
        "en": "A bright light reflection or flash glare is obscuring parts of the document. Please turn off camera flash and tilt the document slightly away from direct overhead light.",
        "hi": "तेज़ रोशनी या फ़्लैश की चमक के कारण दस्तावेज़ का कुछ हिस्सा छिप रहा है। कृपया कैमरे का फ़्लैश बंद करें और दस्तावेज़ को सीधे बल्ब की रोशनी से थोड़ा हटाकर फ़ोटो लें।",
    },
    "IMAGE_TOO_DARK": {
        "en": "The image is too dark or underexposed. Move to a well-lit room or stand near a window to capture clearly.",
        "hi": "फ़ोटो बहुत अंधेरे में लिया गया है। कृपया अच्छी रोशनी वाले कमरे में जाएँ या खिड़की के पास आकर साफ़ फ़ोटो लें।",
    },
    "IMAGE_CROPPED": {
        "en": "One or more corners or edges of the document are cut off. Please step back slightly so the complete card or sheet is inside the frame.",
        "hi": "दस्तावेज़ का एक या अधिक कोना कट गया है। कृपया कैमरे को थोड़ा पीछे रखें ताकि पूरा दस्तावेज़ फ्रेम के अंदर आ जाए।",
    },
    "RESOLUTION_TOO_LOW": {
        "en": "The image resolution is below our minimum standard (at least 400x300 pixels). Please upload the original high-resolution photo or PDF without compressing it.",
        "hi": "फ़ोटो का रिज़ॉल्यूशन न्यूनतम मानक से कम है। कृपया बिना कंप्रेस किए मूल उच्च रिज़ॉल्यूशन वाली तस्वीर या पीडीएफ़ अपलोड करें।",
    },
    "FILE_TOO_SMALL": {
        "en": "The file size is unusually small (under 1KB) and appears corrupt or empty. Please check the file and try again.",
        "hi": "फ़ाइल का आकार बहुत छोटा (1KB से कम) है और ऐसा लगता है कि यह खाली या ख़राब है। कृपया फ़ाइल की जाँच करें और दोबारा प्रयास करें।",
    },
}


def assess_quality(
    meta: Dict,
    client_signals: Optional[Dict] = None,
    slot: Optional[str] = None,
    content: Optional[bytes] = None,
) -> Dict:
    """Assess document image quality deterministically.

    Returns:
        {
            "passed": bool,
            "quality_score": float,  # 0.0 - 1.0
            "issues": List[str],     # Defect codes
            "remediation_en": str,
            "remediation_hi": str,
            "guidance": Dict,
        }
    """
    signals = client_signals or {}
    issues: List[str] = []
    scores: List[float] = []

    # 1. File size checks
    file_size = meta.get("file_size", 0)
    if file_size < 1024:
        issues.append("FILE_TOO_SMALL")
        scores.append(0.1)
    elif file_size < 15000:
        # Suspiciously small for high-res photo, but could be small PDF
        scores.append(0.65)
    else:
        scores.append(0.95)

    # 2. Dimensions & Resolution checks
    width = meta.get("width")
    height = meta.get("height")
    mime = meta.get("mime_type", "")

    if width is not None and height is not None:
        if width < 400 or height < 300:
            issues.append("RESOLUTION_TOO_LOW")
            scores.append(0.4)
        else:
            scores.append(0.95)

        # Aspect ratio check
        aspect = width / max(height, 1)
        if aspect > 4.5 or aspect < 0.22:
            issues.append("IMAGE_CROPPED")
            scores.append(0.45)
        else:
            scores.append(0.95)
    elif mime == "application/pdf":
        scores.append(0.95)

    # 3. Client optical signals integration (if present from camera feed)
    client_blur = signals.get("blur_score")
    if client_blur is not None:
        try:
            b_val = float(client_blur)
            if b_val < 0.65:
                issues.append("IMAGE_BLURRY")
                scores.append(max(0.2, b_val))
            else:
                scores.append(min(1.0, b_val))
        except (ValueError, TypeError):
            pass

    client_glare = signals.get("glare_score")
    if client_glare is not None:
        try:
            g_val = float(client_glare)
            if g_val > 0.45:
                issues.append("IMAGE_GLARE")
                scores.append(max(0.3, 1.0 - g_val))
            else:
                scores.append(0.95)
        except (ValueError, TypeError):
            pass

    client_dark = signals.get("dark_score")
    if client_dark is not None:
        try:
            d_val = float(client_dark)
            if d_val > 0.60:
                issues.append("IMAGE_TOO_DARK")
                scores.append(max(0.3, 1.0 - d_val))
            else:
                scores.append(0.95)
        except (ValueError, TypeError):
            pass

    # 4. Byte entropy / variance check on raw bytes if provided
    if content and len(content) > 512:
        sample = content[:512]
        unique_bytes = len(set(sample))
        if unique_bytes < 16:
            issues.append("IMAGE_TOO_DARK")
            scores.append(0.2)

    # Calculate composite score
    composite_score = round(sum(scores) / len(scores), 2) if scores else 0.85
    passed = composite_score >= QUALITY_PASS_THRESHOLD and len(issues) == 0

    # Pick dominant issue coaching message
    remediation_en = ""
    remediation_hi = ""
    if issues:
        dominant_issue = issues[0]
        coaching = DEFECT_COACHING.get(dominant_issue, {})
        remediation_en = coaching.get("en", "Please upload a clearer image of this document.")
        remediation_hi = coaching.get("hi", "कृपया इस दस्तावेज़ की एक स्पष्ट तस्वीर अपलोड करें।")

    guidance = SLOT_GUIDELINES.get(slot, {}) if slot else {}

    return {
        "passed": passed,
        "quality_score": composite_score,
        "issues": issues,
        "remediation_en": remediation_en,
        "remediation_hi": remediation_hi,
        "guidance": guidance,
    }
