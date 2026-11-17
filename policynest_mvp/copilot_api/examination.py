"""IRDAI Examination System and Assessment Engine for PolicyNest POSP Candidates.

Complies with IRDAI POSP Guidelines 2015:
1. Exam Specifications:
   - Total Questions: 50 Multiple Choice Questions (1 mark each).
   - Exam Duration: 1800 seconds (30 minutes).
   - Passing Threshold: 35% (18 marks out of 50).
   - Syllabus Coverage:
     - Principles of Insurance (10 questions)
     - General Insurance: Motor, Fire, Property (10 questions)
     - Life Insurance: Term, Endowment, ULIPs (10 questions)
     - Health Insurance & Personal Accident (10 questions)
     - POSP Code of Conduct, Ethics & Compliance (10 questions)

2. Strict Anti-Cheating & Server-Side Authority:
   - Server-side authoritative evaluation (scoring keys never sent to client).
   - Tab switching, blur, and incident flagging.
   - Enforced 24-hour retake cooldown on failed attempts.
   - Admin cooldown override for verified technical glitches.
"""
import json
import logging
import random
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

import auth
import policy
import portal

log = logging.getLogger("policynest.examination")

PASS_MARK_REQUIRED = 18  # 35% of 50
TOTAL_QUESTIONS = 50
EXAM_DURATION_SECONDS = 1800  # 30 minutes
COOLDOWN_SECONDS = 86400  # 24 hours


def _check_exam_access(actor: Dict[str, Any], action: str = "exam.start") -> None:
    """Enforce ABAC capability check for examination operations."""
    if not actor or not actor.get("id"):
        raise PermissionError("unauthenticated")

    role = actor.get("role")
    resource = {"applicant_id": actor["id"], "status": "TRAINING_COMPLETE", "sensitivity": "applicant"}

    if role == "applicant":
        if not policy.allows(actor, action, resource):
            raise PermissionError(f"forbidden: applicant lacks '{action}'")
    elif role in ("exam_admin", "compliance_officer", "tech_admin", "admin"):
        return  # Authorized staff personas
    else:
        raise PermissionError(f"forbidden: role '{role}' lacks exam access")


# ------------------------------------------------------------- Default Question Bank (50 Questions)
DEFAULT_QUESTION_BANK = [
    # Category 1: Principles of Insurance (10 Questions)
    {
        "id": "Q-PRIN-01",
        "category": "principles",
        "question_en": "What is the primary foundation of the insurance principle 'Uberrima Fides'?",
        "question_hi": "बीमा सिद्धांत 'उबेरिमा फाइड्स' (परम सद्भाव) का प्राथमिक आधार क्या है?",
        "options_en": ["Utmost Good Faith", "Caveat Emptor", "Strict Liability", "Limited Liability"],
        "options_hi": ["परम सद्भाव", "क्रेता सावधान", "कठोर दायित्व", "सीमित दायित्व"],
        "correct_index": 0,
        "explanation_en": "Uberrima Fides translates to Utmost Good Faith, requiring both parties to disclose all material facts.",
        "explanation_hi": "उबेरिमा फाइड्स का अर्थ परम सद्भाव है, जिसमें दोनों पक्षों को सभी महत्वपूर्ण तथ्यों का खुलासा करना होता है।",
    },
    {
        "id": "Q-PRIN-02",
        "category": "principles",
        "question_en": "Which principle prevents an insured person from profiting from a loss?",
        "question_hi": "कौन सा सिद्धांत बीमित व्यक्ति को नुकसान से अनुचित लाभ कमाने से रोकता है?",
        "options_en": ["Principle of Indemnity", "Principle of Subrogation", "Principle of Contribution", "Principle of Proximate Cause"],
        "options_hi": ["क्षतिपूर्ति का सिद्धांत", "प्रत्यासन का सिद्धांत", "अंशदान का सिद्धांत", "निकटतम कारण का सिद्धांत"],
        "correct_index": 0,
        "explanation_en": "The principle of indemnity ensures the insured is restored to their pre-loss financial position without profit.",
        "explanation_hi": "क्षतिपूर्ति का सिद्धांत यह सुनिश्चित करता है कि बीमित व्यक्ति को बिना किसी लाभ के उसकी पूर्व-हानि वित्तीय स्थिति में बहाल किया जाए।",
    },
    {
        "id": "Q-PRIN-03",
        "category": "principles",
        "question_en": "When must insurable interest exist in a Life Insurance contract?",
        "question_hi": "जीवन बीमा अनुबंध में बीमायोग्य हित (Insurable Interest) कब मौजूद होना चाहिए?",
        "options_en": ["At the time of taking the policy", "At the time of claim only", "Continuously throughout life", "At the time of maturity only"],
        "options_hi": ["पॉलिसी लेते समय", "केवल दावे के समय", "जीवन भर निरंतर", "केवल परिपक्वता के समय"],
        "correct_index": 0,
        "explanation_en": "In life insurance, insurable interest must exist at the time of policy inception.",
        "explanation_hi": "जीवन बीमा में, बीमायोग्य हित पॉलिसी की शुरुआत के समय मौजूद होना चाहिए।",
    },
    {
        "id": "Q-PRIN-04",
        "category": "principles",
        "question_en": "What does the Principle of Subrogation allow an insurer to do?",
        "question_hi": "प्रत्यासन (Subrogation) का सिद्धांत बीमाकर्ता को क्या करने की अनुमति देता है?",
        "options_en": ["Step into the insured's shoes to recover losses from a negligent third party", "Cancel the policy without notice", "Refuse payment of valid claims", "Double the sum insured"],
        "options_hi": ["लापरवाह तीसरे पक्ष से नुकसान की वसूली के लिए बीमित व्यक्ति के कानूनी अधिकार प्राप्त करना", "बिना सूचना पॉलिसी रद्द करना", "वैध दावों के भुगतान से इनकार करना", "बीमा राशि दोगुनी करना"],
        "correct_index": 0,
        "explanation_en": "Subrogation transfers the legal rights of recovery from the insured to the insurer after claim settlement.",
        "explanation_hi": "प्रत्यासन दावा निपटान के बाद वसूली के कानूनी अधिकारों को बीमित व्यक्ति से बीमाकर्ता को हस्तांतरित करता है।",
    },
    {
        "id": "Q-PRIN-05",
        "category": "principles",
        "question_en": "What is 'Proximate Cause' in insurance claim determination?",
        "question_hi": "बीमा दावा निर्धारण में 'निकटतम कारण' (Proximate Cause) क्या है?",
        "options_en": ["The active, efficient cause that sets in motion a train of events without an independent intervention", "The most remote cause of damage", "The time of the accident", "The insured's age"],
        "options_hi": ["वह सक्रिय और प्रभावी कारण जो बिना किसी स्वतंत्र हस्तक्षेप के घटनाओं की श्रृंखला शुरू करता है", "नुकसान का सबसे दूरस्थ कारण", "दुर्घटना का समय", "बीमित व्यक्ति की आयु"],
        "correct_index": 0,
        "explanation_en": "Proximate cause is the dominant, operative cause that directly produces the insured loss.",
        "explanation_hi": "निकटतम कारण वह प्रमुख कारण है जो सीधे बीमित नुकसान का उत्पादन करता है।",
    },
    {
        "id": "Q-PRIN-06",
        "category": "principles",
        "question_en": "Risk pooling in insurance operates primarily on which mathematical concept?",
        "question_hi": "बीमा में जोखिम पूलिंग (Risk Pooling) मुख्य रूप से किस गणितीय अवधारणा पर कार्य करती है?",
        "options_en": ["Law of Large Numbers", "Pythagorean Theorem", "Differential Calculus", "Fibonacci Sequence"],
        "options_hi": ["बड़ी संख्याओं का नियम (Law of Large Numbers)", "पाइथागोरस प्रमेय", "अवकलन गणित", "फाइबोनैचि अनुक्रम"],
        "correct_index": 0,
        "explanation_en": "The Law of Large Numbers allows insurers to predict aggregate claim frequency reliably.",
        "explanation_hi": "बड़ी संख्याओं का नियम बीमाकर्ताओं को कुल दावा आवृत्ति की विश्वसनीय भविष्यवाणी करने की अनुमति देता है।",
    },
    {
        "id": "Q-PRIN-07",
        "category": "principles",
        "question_en": "Which of the following is considered a pure risk?",
        "question_hi": "निम्नलिखित में से किसे शुद्ध जोखिम (Pure Risk) माना जाता है?",
        "options_en": ["Risk of damage to a home by fire", "Investing in the stock market", "Gambling in a casino", "Starting a speculative business"],
        "options_hi": ["आग से घर को नुकसान होने का जोखिम", "शेयर बाजार में निवेश", "कैसीनो में जुआ", "सट्टा व्यवसाय शुरू करना"],
        "correct_index": 0,
        "explanation_en": "Pure risk involves only the possibility of loss or no loss (insurable), whereas speculative risk involves gain.",
        "explanation_hi": "शुद्ध जोखिम में केवल हानि या कोई हानि न होने की संभावना होती है।",
    },
    {
        "id": "Q-PRIN-08",
        "category": "principles",
        "question_en": "In General Insurance, when must insurable interest exist?",
        "question_hi": "सामान्य बीमा में, बीमायोग्य हित कब मौजूद होना चाहिए?",
        "options_en": ["Both at inception and at the time of loss", "At inception only", "At claim settlement only", "Not required in general insurance"],
        "options_hi": ["पॉलिसी लेते समय और नुकसान के समय दोनों", "केवल शुरुआत में", "केवल दावा निपटान के समय", "सामान्य बीमा में आवश्यक नहीं"],
        "correct_index": 0,
        "explanation_en": "In general insurance (e.g. fire/property), insurable interest must exist both at inception and time of loss.",
        "explanation_hi": "सामान्य बीमा में बीमायोग्य हित शुरुआत और हानि के समय दोनों में होना चाहिए।",
    },
    {
        "id": "Q-PRIN-09",
        "category": "principles",
        "question_en": "What happens if a proposer deliberately conceals a pre-existing medical condition?",
        "question_hi": "यदि कोई प्रस्तावक जानबूझकर पहले से मौजूद बीमारी को छुपाता है तो क्या होता है?",
        "options_en": ["Policy becomes voidable at insurer's option due to non-disclosure", "Insurer must pay double the claim", "Premium is automatically refunded with interest", "Policy duration is extended"],
        "options_hi": ["गैर-प्रकटीकरण के कारण पॉलिसी बीमाकर्ता के विकल्प पर अमान्य हो जाती है", "बीमाकर्ता को दोहरा दावा देना होगा", "प्रीमियम ब्याज सहित वापस किया जाता है", "पॉलिसी की अवधि बढ़ जाती है"],
        "correct_index": 0,
        "explanation_en": "Concealment of material facts breaches utmost good faith, making the contract voidable.",
        "explanation_hi": "महत्वपूर्ण तथ्यों को छुपाना परम सद्भाव का उल्लंघन है, जिससे अनुबंध रद्द किया जा सकता है।",
    },
    {
        "id": "Q-PRIN-10",
        "category": "principles",
        "question_en": "What is the primary role of a Point of Sales Person (POSP)?",
        "question_hi": "प्वाइंट ऑफ सेल्स पर्सन (POSP) की प्राथमिक भूमिका क्या है?",
        "options_en": ["Solicit and market pre-underwritten, simplified insurance products", "Underwrite complex corporate reinsurance", "Invest company reserve funds", "Approve insurance company mergers"],
        "options_hi": ["पूर्व-अंडरराइट और सरल बीमा उत्पादों का विपणन और बिक्री करना", "जटिल कॉर्पोरेट पुनर्बीमा करना", "कंपनी के रिजर्व फंड का निवेश करना", "बीमा कंपनी के विलय को मंजूरी देना"],
        "correct_index": 0,
        "explanation_en": "POSP agents are certified to market straightforward, pre-underwritten products defined by IRDAI.",
        "explanation_hi": "पीओएसपी एजेंट IRDAI द्वारा परिभाषित सरल और पूर्व-अंडरराइट उत्पादों का विपणन करने के लिए प्रमाणित हैं।",
    },

    # Category 2: General Insurance (10 Questions)
    {
        "id": "Q-GEN-01",
        "category": "general",
        "question_en": "Under the Motor Vehicles Act 2019, which insurance cover is statutory and mandatory for all motor vehicles?",
        "question_hi": "मोटर वाहन अधिनियम 2019 के तहत, सभी मोटर वाहनों के लिए कौन सा बीमा कवर वैधानिक और अनिवार्य है?",
        "options_en": ["Third-Party Liability Insurance", "Zero Depreciation Cover", "Engine Protector Cover", "Consumables Cover"],
        "options_hi": ["तृतीय पक्ष देयता (थर्ड पार्टी) बीमा", "जीरो डेप्रिसिएशन कवर", "इंजन प्रोटेक्टर कवर", "कंज्यूमेबल्स कवर"],
        "correct_index": 0,
        "explanation_en": "Third-party motor insurance is legally mandatory for all motor vehicles plying on Indian roads.",
        "explanation_hi": "भारतीय सड़कों पर चलने वाले सभी वाहनों के लिए थर्ड पार्टी मोटर बीमा कानूनी रूप से अनिवार्य है।",
    },
    {
        "id": "Q-GEN-02",
        "category": "general",
        "question_en": "What does 'Own Damage' (OD) cover in a comprehensive motor insurance policy?",
        "question_hi": "व्यापक (कॉम्प्रिहेंसिव) मोटर बीमा पॉलिसी में 'ओन डैमेज' (OD) क्या कवर करता है?",
        "options_en": ["Accidental damage, fire, and theft of the insured's own vehicle", "Third party bodily injury only", "Traffic fines and penalties", "Fuel replacement costs"],
        "options_hi": ["बीमित व्यक्ति के अपने वाहन को दुर्घटना, आग और चोरी से होने वाला नुकसान", "केवल तीसरे पक्ष की शारीरिक चोट", "यातायात जुर्माना और दंड", "ईंधन बदलने की लागत"],
        "correct_index": 0,
        "explanation_en": "Own damage covers loss or damage to the insured vehicle itself due to accident, fire, theft, or natural calamities.",
        "explanation_hi": "ओन डैमेज दुर्घटना, आग, चोरी या प्राकृतिक आपदाओं के कारण बीमित वाहन के नुकसान को कवर करता है।",
    },
    {
        "id": "Q-GEN-03",
        "category": "general",
        "question_en": "What is 'No Claim Bonus' (NCB) in motor insurance?",
        "question_hi": "मोटर बीमा में 'नो क्लेम बोनस' (NCB) क्या है?",
        "options_en": ["A discount on Own Damage premium rewarded for a claim-free policy year", "A cash refund sent to the driver", "A penalty for filing a claim", "An interest charge on late payments"],
        "options_hi": ["दावा-मुक्त पॉलिसी वर्ष के लिए ओन डैमेज प्रीमियम पर दी जाने वाली छूट", "ड्राइवर को भेजा गया नकद रिफंड", "दावा दायर करने पर जुर्माना", "देर से भुगतान पर ब्याज"],
        "correct_index": 0,
        "explanation_en": "NCB rewards safe driving with discounts ranging from 20% to 50% on Own Damage premium.",
        "explanation_hi": "एनसीबी ओन डैमेज प्रीमियम पर 20% से 50% तक की छूट के साथ सुरक्षित ड्राइविंग को पुरस्कृत करता है।",
    },
    {
        "id": "Q-GEN-04",
        "category": "general",
        "question_en": "Can No Claim Bonus (NCB) be transferred when a person sells their car and buys a new one?",
        "question_hi": "क्या कोई व्यक्ति अपनी कार बेचकर नई कार खरीदते समय नो क्लेम बोनस (NCB) स्थानांतरित कर सकता है?",
        "options_en": ["Yes, NCB belongs to the insured individual, not the vehicle", "No, NCB remains with the old car", "Only if the car is sold to a relative", "NCB is canceled upon sale"],
        "options_hi": ["हाँ, NCB बीमित व्यक्ति का होता है, वाहन का नहीं", "नहीं, NCB पुरानी कार के साथ ही रहता है", "केवल तभी जब कार किसी रिश्तेदार को बेची जाए", "बिक्री पर NCB रद्द हो जाता है"],
        "correct_index": 0,
        "explanation_en": "NCB is earned by the policyholder and can be transferred to a new vehicle owned by the same person.",
        "explanation_hi": "NCB पॉलिसीधारक द्वारा अर्जित किया जाता है और उसी व्यक्ति के नए वाहन में स्थानांतरित किया जा सकता है।",
    },
    {
        "id": "Q-GEN-05",
        "category": "general",
        "question_en": "What does a 'Zero Depreciation' (Bumper-to-Bumper) add-on cover do?",
        "question_hi": "'जीरो डेप्रिसिएशन' (बम्पर-टू-बम्पर) ऐड-ऑन कवर क्या करता है?",
        "options_en": ["Waives depreciation deductions on replaced parts (plastic, rubber, metal) during claim settlement", "Guarantees free fuel for one year", "Covers speeding fines", "Replaces the car every two years"],
        "options_hi": ["दावा निपटान के दौरान बदले गए पुर्जों (प्लास्टिक, रबर, धातु) पर मूल्यह्रास कटौती को माफ करता है", "एक साल के लिए मुफ्त ईंधन की गारंटी", "तेज गति के जुर्माने को कवर करता है", "हर दो साल में कार बदलता है"],
        "correct_index": 0,
        "explanation_en": "Zero depreciation covers 100% replacement cost of parts without deducting standard depreciation percentages.",
        "explanation_hi": "जीरो डेप्रिसिएशन मानक मूल्यह्रास काटे बिना पुर्जों की 100% प्रतिस्थापन लागत को कवर करता है।",
    },
    {
        "id": "Q-GEN-06",
        "category": "general",
        "question_en": "Standard Fire and Special Perils Policy (SFSP) covers damage caused by which of the following?",
        "question_hi": "मानक आग और विशेष संकट पॉलिसी (SFSP) निम्नलिखित में से किसके कारण होने वाले नुकसान को कवर करती है?",
        "options_en": ["Lightning, explosion, storm, flood, and inundation", "Normal wear and tear", "War and nuclear risks", "Willful destruction by owner"],
        "options_hi": ["आकाशीय बिजली, विस्फोट, तूफान, बाढ़ और जलप्लावन", "सामान्य टूट-फूट", "युद्ध और परमाणु जोखिम", "मालिक द्वारा जानबूझकर किया गया विनाश"],
        "correct_index": 0,
        "explanation_en": "SFSP covers fire, lightning, explosion, storm, cyclone, flood, and civil unrest perils.",
        "explanation_hi": "एसएफएसपी आग, बिजली, विस्फोट, तूफान, चक्रवात और बाढ़ के संकट को कवर करता है।",
    },
    {
        "id": "Q-GEN-07",
        "category": "general",
        "question_en": "What is the maximum Sum Insured permitted for a POSP under standard pre-underwritten Home Insurance?",
        "question_hi": "मानक होम इंश्योरेंस के तहत एक POSP के लिए अधिकतम अनुमत बीमा राशि क्या है?",
        "options_en": ["Up to IRDAI prescribed POSP product limits (typically ₹1 Crore for dwellings)", "Unlimited", "Maximum ₹50,000", "Maximum ₹1 Lakh"],
        "options_hi": ["IRDAI द्वारा निर्धारित सीमा तक (आमतौर पर आवास के लिए ₹1 करोड़ तक)", "असीमित", "अधिकतम ₹50,000", "अधिकतम ₹1 लाख"],
        "correct_index": 0,
        "explanation_en": "IRDAI guidelines specify sum insured caps for POSP non-life product distribution.",
        "explanation_hi": "IRDAI दिशानिर्देश POSP वितरण के लिए बीमा राशि सीमा निर्धारित करते हैं।",
    },
    {
        "id": "Q-GEN-08",
        "category": "general",
        "question_en": "What is 'Compulsory Deductible' in a motor insurance claim?",
        "question_hi": "मोटर बीमा दावे में 'अनिवार्य कटौती' (Compulsory Deductible) क्या है?",
        "options_en": ["A fixed amount that the policyholder must pay from their pocket for every claim", "The total commission of the agent", "The annual tax on the vehicle", "The cost of vehicle registration"],
        "options_hi": ["एक निश्चित राशि जो पॉलिसीधारक को प्रत्येक दावे के लिए अपनी जेब से चुकानी होगी", "एजेंट का कुल कमीशन", "वाहन पर वार्षिक कर", "वाहन पंजीकरण की लागत"],
        "correct_index": 0,
        "explanation_en": "Compulsory deductible is statutory (e.g. ₹1,000 for 4-wheelers up to 1500cc) borne by the insured.",
        "explanation_hi": "अनिवार्य कटौती प्रत्येक दावे पर बीमित व्यक्ति द्वारा वहन की जाने वाली न्यूनतम राशि है।",
    },
    {
        "id": "Q-GEN-09",
        "category": "general",
        "question_en": "What does a Shopkeeper Package Policy typically bundle?",
        "question_hi": "शॉपकीपर पैकेज पॉलिसी आमतौर पर क्या बंडल करती है?",
        "options_en": ["Fire, burglary, plate glass, money in transit, and public liability", "Only employee life insurance", "Only overseas travel", "Only motor third-party cover"],
        "options_hi": ["आग, चोरी, प्लेट ग्लास, ट्रांजिट में नकदी और सार्वजनिक देयता", "केवल कर्मचारी जीवन बीमा", "केवल विदेश यात्रा", "केवल मोटर थर्ड पार्टी कवर"],
        "correct_index": 0,
        "explanation_en": "Shopkeeper package policies provide comprehensive multi-peril protection for retail enterprises.",
        "explanation_hi": "दुकानदार पैकेज नीतियां खुदरा उद्यमों के लिए बहु-संकट सुरक्षा प्रदान करती हैं।",
    },
    {
        "id": "Q-GEN-10",
        "category": "general",
        "question_en": "What is the consequence of driving an uninsured vehicle on public roads in India?",
        "question_hi": "भारत में सार्वजनिक सड़कों पर बिना बीमा वाला वाहन चलाने का क्या परिणाम है?",
        "options_en": ["Fines up to ₹2,000 to ₹4,000 and/or imprisonment under Motor Vehicles Act", "A congratulatory letter from the transport authority", "Free vehicle registration renewal", "Zero penalty"],
        "options_hi": ["मोटर वाहन अधिनियम के तहत ₹2,000 से ₹4,000 तक का जुर्माना और/या कारावास", "परिवहन प्राधिकरण से बधाई पत्र", "मुफ्त वाहन पंजीकरण नवीनीकरण", "शून्य जुर्माना"],
        "correct_index": 0,
        "explanation_en": "Section 196 of the Motor Vehicles Act penalizes driving an uninsured vehicle with hefty fines and imprisonment.",
        "explanation_hi": "मोटर वाहन अधिनियम की धारा 196 बिना बीमा वाले वाहन चलाने पर भारी जुर्माना और कारावास का प्रावधान करती है।",
    },

    # Category 3: Life Insurance (10 Questions)
    {
        "id": "Q-LIFE-01",
        "category": "life",
        "question_en": "What is 'Term Life Insurance' primarily designed to provide?",
        "question_hi": "'टर्म लाइफ इंश्योरेंस' मुख्य रूप से क्या प्रदान करने के लिए डिज़ाइन किया गया है?",
        "options_en": ["Pure financial protection for beneficiaries in the event of the insured's untimely death", "Stock market investment returns", "Guaranteed loan disbursement", "Pension after age 50 without death benefit"],
        "options_hi": ["बीमित व्यक्ति की असामयिक मृत्यु की स्थिति में लाभार्थियों के लिए शुद्ध वित्तीय सुरक्षा", "शेयर बाजार निवेश रिटर्न", "गारंटीकृत ऋण संवितरण", "मृत्यु लाभ के बिना 50 वर्ष की आयु के बाद पेंशन"],
        "correct_index": 0,
        "explanation_en": "Term life insurance is pure risk protection without investment/savings components.",
        "explanation_hi": "टर्म इंश्योरेंस बचत या निवेश घटकों के बिना शुद्ध जीवन जोखिम सुरक्षा है।",
    },
    {
        "id": "Q-LIFE-02",
        "category": "life",
        "question_en": "What is 'Human Life Value' (HLV)?",
        "question_hi": "'मानव जीवन मूल्य' (HLV) क्या है?",
        "options_en": ["The present monetary value of expected future net earnings of an individual available to their dependents", "The hospital billing value of a patient", "The cost of life insurance premium", "The income tax paid by a citizen"],
        "options_hi": ["किसी व्यक्ति की भविष्य की अपेक्षित शुद्ध कमाई का वर्तमान मौद्रिक मूल्य जो उसके आश्रितों के लिए उपलब्ध होगा", "मरीज का अस्पताल बिलिंग मूल्य", "जीवन बीमा प्रीमियम की लागत", "नागरिक द्वारा भुगतान किया गया आयकर"],
        "correct_index": 0,
        "explanation_en": "HLV calculates the appropriate amount of life insurance protection a family breadwinner requires.",
        "explanation_hi": "एचएलवी यह गणना करता है कि किसी परिवार के कमाने वाले सदस्य को कितनी जीवन बीमा सुरक्षा की आवश्यकता है।",
    },
    {
        "id": "Q-LIFE-03",
        "category": "life",
        "question_en": "What is the 'Grace Period' for premium payment in Life Insurance policies?",
        "question_hi": "जीवन बीमा पॉलिसियों में प्रीमियम भुगतान के लिए 'ग्रेस पीरियड' (रियायती अवधि) क्या है?",
        "options_en": ["30 days for yearly/half-yearly and 15 days for monthly mode without policy lapse", "6 months", "1 year", "Zero days"],
        "options_hi": ["वार्षिक/छमाही के लिए 30 दिन और मासिक मोड के लिए 15 दिन बिना पॉलिसी लैप्स हुए", "6 महीने", "1 साल", "शून्य दिन"],
        "correct_index": 0,
        "explanation_en": "IRDAI mandates a grace period of 30 days (15 days for monthly mode) during which cover remains intact.",
        "explanation_hi": "IRDAI 30 दिनों की रियायती अवधि अनिवार्य करता है जिसके दौरान बीमा कवर बरकरार रहता है।",
    },
    {
        "id": "Q-LIFE-04",
        "category": "life",
        "question_en": "What happens if death occurs during the grace period of a life insurance policy?",
        "question_hi": "यदि जीवन बीमा पॉलिसी की ग्रेस पीरियड के दौरान मृत्यु हो जाती है तो क्या होता है?",
        "options_en": ["Claim is paid in full after deducting the unpaid premium", "Claim is completely rejected", "Only 10% is paid", "Policy is cancelled retroactively"],
        "options_hi": ["बकाया प्रीमियम घटाकर पूरा दावा अदा किया जाता है", "दावा पूरी तरह खारिज कर दिया जाता है", "केवल 10% का भुगतान किया जाता है", "पॉलिसी को पूर्वव्यापी रूप से रद्द कर दिया जाता है"],
        "correct_index": 0,
        "explanation_en": "The policy remains active during the grace period, so death claims are settled net of unpaid premium.",
        "explanation_hi": "ग्रेस पीरियड के दौरान पॉलिसी सक्रिय रहती है, इसलिए बकाया प्रीमियम काटकर दावा दिया जाता है।",
    },
    {
        "id": "Q-LIFE-05",
        "category": "life",
        "question_en": "What is a 'Unit Linked Insurance Plan' (ULIP)?",
        "question_hi": "'यूनिट लिंक्ड इंश्योरेंस प्लान' (ULIP) क्या है?",
        "options_en": ["An integrated product combining life insurance protection with equity/debt capital market investment", "A fixed savings deposit in a bank", "A health-only hospitalization card", "A motor insurance policy"],
        "options_hi": ["एक एकीकृत उत्पाद जो जीवन बीमा सुरक्षा को इक्विटी/ऋण पूंजी बाजार निवेश के साथ जोड़ता है", "बैंक में एक निश्चित बचत जमा", "केवल स्वास्थ्य अस्पताल कार्ड", "एक मोटर बीमा पॉलिसी"],
        "correct_index": 0,
        "explanation_en": "ULIP premiums are split between life insurance coverage and market-linked fund units.",
        "explanation_hi": "यूलिप में प्रीमियम का एक हिस्सा जीवन बीमा कवर में और दूसरा हिस्सा बाजार फंड में निवेश होता है।",
    },
    {
        "id": "Q-LIFE-06",
        "category": "life",
        "question_en": "Under a Pure Endowment policy, when is the sum insured paid?",
        "question_hi": "शुद्ध बंदोबस्ती (Pure Endowment) पॉलिसी के तहत, बीमा राशि का भुगतान कब किया जाता है?",
        "options_en": ["Only if the insured survives the specified policy term", "Immediately upon death only", "Every week", "Never"],
        "options_hi": ["केवल तभी जब बीमित व्यक्ति निर्दिष्ट पॉलिसी अवधि तक जीवित रहता है", "केवल मृत्यु पर तुरंत", "हर हफ्ते", "कभी नहीं"],
        "correct_index": 0,
        "explanation_en": "A pure endowment pays the sum insured only upon survival to the maturity date.",
        "explanation_hi": "प्योर एंडोमेंट केवल परिपक्वता तिथि तक जीवित रहने पर बीमा राशि का भुगतान करता है।",
    },
    {
        "id": "Q-LIFE-07",
        "category": "life",
        "question_en": "What is an 'Accidental Death Benefit' (ADB) rider?",
        "question_hi": "'आकस्मिक मृत्यु लाभ' (ADB) राइडर क्या है?",
        "options_en": ["An add-on providing an additional sum insured if death occurs due to an accident", "A health discount voucher", "A motor car repair service", "Free dental checkup"],
        "options_hi": ["एक ऐड-ऑन जो दुर्घटना के कारण मृत्यु होने पर अतिरिक्त बीमा राशि प्रदान करता है", "स्वास्थ्य छूट वाउचर", "मोटर कार मरम्मत सेवा", "मुफ्त दंत परीक्षण"],
        "correct_index": 0,
        "explanation_en": "ADB riders pay an extra benefit over and above the base life cover if death is caused by an accident.",
        "explanation_hi": "एडीबी राइडर दुर्घटना से मृत्यु होने पर मूल जीवन कवर के ऊपर अतिरिक्त लाभ का भुगतान करता है।",
    },
    {
        "id": "Q-LIFE-08",
        "category": "life",
        "question_en": "What is the 'Free Look Period' in a Life Insurance policy?",
        "question_hi": "जीवन बीमा पॉलिसी में 'फ्री लुक पीरियड' (Free Look Period) क्या है?",
        "options_en": ["A period of 15 to 30 days to review policy terms and return it for a refund if dissatisfied", "Free policy for 5 years", "Period with no premium requirement", "Trial period for agents"],
        "options_hi": ["पॉलिसी की शर्तों की समीक्षा करने और असंतुष्ट होने पर रिफंड के लिए वापस करने की 15 से 30 दिनों की अवधि", "5 साल के लिए मुफ्त पॉलिसी", "बिना प्रीमियम की अवधि", "एजेंटों के लिए परीक्षण अवधि"],
        "correct_index": 0,
        "explanation_en": "IRDAI gives policyholders 15 days (30 days for distance marketing) to return a policy without penalty.",
        "explanation_hi": "IRDAI पॉलिसीधारकों को पॉलिसी प्राप्त होने के 15 दिनों के भीतर रद्द करने का अधिकार देता है।",
    },
    {
        "id": "Q-LIFE-09",
        "category": "life",
        "question_en": "What is the 'Claim Settlement Ratio' (CSR) of an insurance company?",
        "question_hi": "एक बीमा कंपनी का 'दावा निपटान अनुपात' (CSR) क्या है?",
        "options_en": ["The percentage of total claims received that the company successfully settled in a financial year", "The interest rate on loans", "The dividend paid to shareholders", "The commission rate of agents"],
        "options_hi": ["एक वित्तीय वर्ष में कंपनी द्वारा सफलतापूर्वक निपटाए गए कुल दावों का प्रतिशत", "ऋण पर ब्याज दर", "शेयरधारकों को दिया गया लाभांश", "एजेंटों की कमीशन दर"],
        "correct_index": 0,
        "explanation_en": "CSR indicates the insurer's track record in honoring and paying claims to policyholders.",
        "explanation_hi": "सीएसआर पॉलिसीधारकों के दावों का सम्मान करने और भुगतान करने में बीमाकर्ता के रिकॉर्ड को दर्शाता है।",
    },
    {
        "id": "Q-LIFE-10",
        "category": "life",
        "question_en": "Under Section 45 of the Insurance Act 1938, after how many years can a life insurance policy NOT be questioned on any ground?",
        "question_hi": "बीमा अधिनियम 1938 की धारा 45 के तहत, कितने वर्षों के बाद जीवन बीमा पॉलिसी पर किसी भी आधार पर सवाल नहीं उठाया जा सकता है?",
        "options_en": ["3 years", "10 years", "1 year", "5 years"],
        "options_hi": ["3 वर्ष", "10 वर्ष", "1 वर्ष", "5 वर्ष"],
        "correct_index": 0,
        "explanation_en": "Section 45 provides indisputability after 3 years from issuance or revival.",
        "explanation_hi": "धारा 45 जारी होने या पुनरुद्धार के 3 वर्ष बाद किसी भी आधार पर पॉलिसी पर सवाल उठाने पर रोक लगाती है।",
    },

    # Category 4: Health & Personal Accident (10 Questions)
    {
        "id": "Q-HLTH-01",
        "category": "health",
        "question_en": "What is a 'Cashless Facility' in health insurance?",
        "question_hi": "स्वास्थ्य बीमा में 'कैशलेस सुविधा' क्या है?",
        "options_en": ["Direct settlement of eligible medical expenses between the insurer/TPA and the network hospital", "Withdrawing money from an ATM without a card", "Paying hospital bills in physical cash", "Free ambulance service only"],
        "options_hi": ["बीमाकर्ता/टीपीए और नेटवर्क अस्पताल के बीच पात्र चिकित्सा खर्चों का सीधा निपटान", "कार्ड के बिना एटीएम से पैसे निकालना", "अस्पताल के बिलों का नकद भुगतान करना", "केवल मुफ्त एम्बुलेंस सेवा"],
        "correct_index": 0,
        "explanation_en": "Cashless facility relieves the patient from paying upfront medical bills at empaneled network hospitals.",
        "explanation_hi": "कैशलेस सुविधा नेटवर्क अस्पतालों में मरीज को अग्रिम बिलों का भुगतान करने से मुक्त करती है।",
    },
    {
        "id": "Q-HLTH-02",
        "category": "health",
        "question_en": "What is an 'Initial Waiting Period' in a standard retail health insurance policy?",
        "question_hi": "एक मानक स्वास्थ्य बीमा पॉलिसी में 'प्रारंभिक प्रतीक्षा अवधि' (Initial Waiting Period) क्या है?",
        "options_en": ["A 30-day period from inception during which no illness claims are covered (accidents covered immediately)", "A 5-year waiting period for all diseases", "Waiting for the physical policy document to arrive", "Time taken to cash a cheque"],
        "options_hi": ["शुरुआत से 30 दिनों की अवधि जिसके दौरान बीमारी के दावों को कवर नहीं किया जाता है (दुर्घटनाएं तुरंत कवर होती हैं)", "सभी बीमारियों के लिए 5 साल की प्रतीक्षा अवधि", "पॉलिसी दस्तावेज आने का इंतजार", "चेक भुनाने में लगा समय"],
        "correct_index": 0,
        "explanation_en": "Standard health policies enforce a 30-day initial waiting period for illnesses to prevent adverse selection.",
        "explanation_hi": "प्रारंभिक 30 दिनों में केवल दुर्घटनाएं कवर होती हैं, बीमारियां नहीं।",
    },
    {
        "id": "Q-HLTH-03",
        "category": "health",
        "question_en": "What is a 'Pre-Existing Disease' (PED) under IRDAI guidelines?",
        "question_hi": "IRDAI दिशानिर्देशों के तहत 'पहले से मौजूद बीमारी' (PED) क्या है?",
        "options_en": ["Any condition diagnosed or treated by a physician within 36 to 48 months prior to policy issuance", "A common cold caught yesterday", "Any disease developed after 10 years of policy", "A condition that only occurs in old age"],
        "options_hi": ["पॉलिसी जारी होने से 36 से 48 महीने पहले किसी चिकित्सक द्वारा निदान या इलाज की गई कोई भी स्थिति", "कल हुआ सामान्य जुकाम", "पॉलिसी के 10 साल बाद विकसित कोई भी बीमारी", "ऐसी स्थिति जो केवल वृद्धावस्था में होती है"],
        "correct_index": 0,
        "explanation_en": "PED refers to medical conditions that existed prior to policy inception within the statutory lookback window.",
        "explanation_hi": "पीईडी का अर्थ उन चिकित्सीय स्थितियों से है जो पॉलिसी शुरू होने से पहले मौजूद थीं।",
    },
    {
        "id": "Q-HLTH-04",
        "category": "health",
        "question_en": "What does 'Co-payment' mean in health insurance?",
        "question_hi": "स्वास्थ्य बीमा में 'सह-भुगतान' (Co-payment) का क्या अर्थ है?",
        "options_en": ["A cost-sharing agreement where the insured pays a specified percentage (e.g. 10% or 20%) of the claim", "The salary paid to hospital doctors", "Premium shared between two friends", "A government tax on medicine"],
        "options_hi": ["एक लागत-साझाकरण व्यवस्था जहां बीमित व्यक्ति दावे का एक निर्दिष्ट प्रतिशत (जैसे 10% या 20%) चुकाता है", "अस्पताल के डॉक्टरों को दिया जाने वाला वेतन", "दो दोस्तों के बीच प्रीमियम का बंटवारा", "दवा पर सरकारी कर"],
        "correct_index": 0,
        "explanation_en": "Co-payment requires the insured to share a predetermined percentage of admissible medical costs.",
        "explanation_hi": "सह-भुगतान के तहत बीमित व्यक्ति दावे की राशि का एक निश्चित प्रतिशत स्वयं वहन करता है।",
    },
    {
        "id": "Q-HLTH-05",
        "category": "health",
        "question_en": "What are 'Pre-Hospitalization Expenses'?",
        "question_hi": "'अस्पताल में भर्ती से पूर्व के खर्च' (Pre-Hospitalization Expenses) क्या हैं?",
        "options_en": ["Medical expenses (consultations, diagnostic tests) incurred up to 30 or 60 days before hospital admission for the relevant illness", "Expenses incurred on wedding gifts", "Buying an ambulance", "Hotel stays during vacation"],
        "options_hi": ["संबंधित बीमारी के लिए अस्पताल में भर्ती होने से 30 या 60 दिन पहले तक के चिकित्सा खर्च (परामर्श, परीक्षण)", "शादी के तोहफों पर किया गया खर्च", "एंबुलेंस खरीदना", "छुट्टियों के दौरान होटल में ठहरना"],
        "correct_index": 0,
        "explanation_en": "Pre-hospitalization covers investigative and diagnostic expenses directly leading to hospital admission.",
        "explanation_hi": "अस्पताल में भर्ती होने से पहले बीमारी की जांच और परीक्षण पर हुए खर्च को कवर किया जाता है।",
    },
    {
        "id": "Q-HLTH-06",
        "category": "health",
        "question_en": "What are 'Day Care Procedures' in modern health insurance?",
        "question_hi": "आधुनिक स्वास्थ्य बीमा में 'डे केयर प्रक्रियाएं' क्या हैं?",
        "options_en": ["Medical treatments or surgeries requiring less than 24 hours hospitalization due to advanced technology (e.g. Cataract, Dialysis)", "Baby day care facilities", "Elderly nursing homes", "Routine dental flossing"],
        "options_hi": ["उन्नत तकनीक के कारण 24 घंटे से कम अस्पताल में भर्ती की आवश्यकता वाले उपचार या सर्जरी (उदा. मोतियाबिंद, डायलिसिस)", "शिशु देखभाल सुविधाएं", "बुजुर्गों के वृद्धाश्रम", "नियमित दांतों की सफाई"],
        "correct_index": 0,
        "explanation_en": "Day care treatments do not require 24-hour admission because of technological advancements.",
        "explanation_hi": "उन्नत तकनीक के कारण 24 घंटे भर्ती रहे बिना होने वाली सर्जरी डे केयर में आती हैं।",
    },
    {
        "id": "Q-HLTH-07",
        "category": "health",
        "question_en": "In Personal Accident insurance, what does 'Permanent Total Disablement' (PTD) compensate?",
        "question_hi": "व्यक्तिगत दुर्घटना बीमा में, 'स्थायी कुल विकलांगता' (PTD) क्या मुआवजा देती है?",
        "options_en": ["100% of the Capital Sum Insured for irreversible loss of both limbs, both eyes, or complete paralysis", "Free taxi rides", "A small box of band-aids", "Discount on gym memberships"],
        "options_hi": ["दोनों अंगों, दोनों आंखों के अपरिवर्तनीय नुकसान या पूर्ण पक्षाघात के लिए 100% बीमा राशि", "मुफ्त टैक्सी की सवारी", "बैंड-एड का एक छोटा सा बॉक्स", "जिम सदस्यता पर छूट"],
        "correct_index": 0,
        "explanation_en": "PTD compensates 100% CSI when an accidental injury permanently incapacitates the individual from earning.",
        "explanation_hi": "पीटीडी दोनों हाथ, दोनों पैर या दोनों आंखें खोने पर 100% बीमा राशि का भुगतान करता है।",
    },
    {
        "id": "Q-HLTH-08",
        "category": "health",
        "question_en": "What is 'Portability' in retail Health Insurance?",
        "question_hi": "स्वास्थ्य बीमा में 'पोर्टेबिलिटी' (Portability) क्या है?",
        "options_en": ["The right of a policyholder to transfer their policy to another insurer while retaining accrued waiting period credits", "Carrying a paper policy in a pocket", "Transferring a mobile phone SIM card", "Selling insurance policies at railway stations"],
        "options_hi": ["पॉलिसीधारक का अर्जित प्रतीक्षा अवधि लाभों को बनाए रखते हुए किसी अन्य बीमाकर्ता को पॉलिसी स्थानांतरित करने का अधिकार", "जेब में कागजी पॉलिसी ले जाना", "मोबाइल फोन सिम कार्ड ट्रांसफर करना", "रेलवे स्टेशनों पर पॉलिसी बेचना"],
        "correct_index": 0,
        "explanation_en": "Portability protects continuity benefits like PED waiting periods when switching insurers.",
        "explanation_hi": "पोर्टेबिलिटी बिना प्रतीक्षा अवधि गंवाए बीमा कंपनी बदलने का अधिकार देती है।",
    },
    {
        "id": "Q-HLTH-09",
        "category": "health",
        "question_en": "What does a 'Cumulative Bonus' in Health Insurance provide?",
        "question_hi": "स्वास्थ्य बीमा में 'संचयी बोनस' (Cumulative Bonus) क्या प्रदान करता है?",
        "options_en": ["An increase in the Sum Insured without any increase in premium for each claim-free year", "A cash voucher sent by post", "Discount on groceries", "Free air travel tickets"],
        "options_hi": ["प्रत्येक दावा-मुक्त वर्ष के लिए प्रीमियम बढ़ाए बिना बीमा राशि में वृद्धि", "डाक द्वारा भेजा गया नकद वाउचर", "किराने के सामान पर छूट", "मुफ्त हवाई यात्रा टिकट"],
        "correct_index": 0,
        "explanation_en": "Cumulative bonus rewards healthy, claim-free years by enhancing the sum insured automatically.",
        "explanation_hi": "दावा-मुक्त वर्ष के लिए बिना प्रीमियम बढ़ाए बीमा कवर की राशि बढ़ जाती है।",
    },
    {
        "id": "Q-HLTH-10",
        "category": "health",
        "question_en": "What role does a Third Party Administrator (TPA) play in health insurance?",
        "question_hi": "स्वास्थ्य बीमा में थर्ड पार्टी एडमिनिस्ट्रेटर (TPA) क्या भूमिका निभाता है?",
        "options_en": ["Facilitates hospital cashless approvals and claims processing on behalf of insurance companies", "Sells second-hand cars", "Issues passports to citizens", "Manufactures surgical instruments"],
        "options_hi": ["बीमा कंपनियों की ओर से अस्पताल में कैशलेस अनुमोदन और दावा प्रसंस्करण की सुविधा प्रदान करता है", "पुरानी कारें बेचता है", "नागरिकों को पासपोर्ट जारी करता है", "सर्जिकल उपकरणों का निर्माण करता है"],
        "correct_index": 0,
        "explanation_en": "TPAs are licensed by IRDAI to manage health claims processing, hospital networks, and approvals.",
        "explanation_hi": "टीपीए अस्पतालों और बीमाकर्ताओं के बीच कैशलेस और दावा निपटान का समन्वय करता है।",
    },

    # Category 5: POSP Code of Conduct & Ethics (10 Questions)
    {
        "id": "Q-ETH-01",
        "category": "ethics",
        "question_en": "Under Section 41 of the Insurance Act 1938, what is 'Rebating'?",
        "question_hi": "बीमा अधिनियम 1938 की धारा 41 के तहत 'रिबेटिंग' (Rebating) क्या है?",
        "options_en": ["Offering any inducement or sharing commission with a client to purchase insurance (strictly illegal)", "Giving a polite greeting to a client", "Explaining policy terms truthfully", "Delivering a physical policy document"],
        "options_hi": ["बीमा खरीदने के लिए ग्राहक को किसी भी प्रकार का प्रलोभन देना या कमीशन साझा करना (सख्त अवैध)", "ग्राहक का विनम्र अभिवादन करना", "पॉलिसी की शर्तों को सच्चाई से समझाना", "भौतिक पॉलिसी दस्तावेज वितरित करना"],
        "correct_index": 0,
        "explanation_en": "Section 41 strictly prohibits offering rebates of commission as an inducement to take out insurance.",
        "explanation_hi": "धारा 41 बीमा कराने के प्रलोभन के रूप में कमीशन में छूट देने पर पूर्ण प्रतिबंध लगाती है।",
    },
    {
        "id": "Q-ETH-02",
        "category": "ethics",
        "question_en": "What is the penalty for rebating under Section 41 of the Insurance Act?",
        "question_hi": "बीमा अधिनियम की धारा 41 के तहत रिबेटिंग के लिए क्या जुर्माना है?",
        "options_en": ["Fine up to ₹10 Lakhs and cancellation of license", "A certificate of appreciation", "Zero penalty", "Free lunch at IRDAI office"],
        "options_hi": ["₹10 लाख तक का जुर्माना और लाइसेंस रद्द होना", "प्रशंसा प्रमाण पत्र", "शून्य जुर्माना", "आईआरडीएआई कार्यालय में मुफ्त दोपहर का भोजन"],
        "correct_index": 0,
        "explanation_en": "Any person who defaults in complying with Section 41 is punishable with a fine which may extend to ₹10 Lakhs.",
        "explanation_hi": "धारा 41 का उल्लंघन करने पर ₹10 लाख तक का जुर्माना लगाया जा सकता है।",
    },
    {
        "id": "Q-ETH-03",
        "category": "ethics",
        "question_en": "Can a POSP be registered with more than one Life Insurer or more than one Broker simultaneously?",
        "question_hi": "क्या कोई POSP एक साथ एक से अधिक जीवन बीमाकर्ता या एक से अधिक ब्रोकर के साथ पंजीकृत हो सकता है?",
        "options_en": ["No, a POSP can only be appointed by one insurer or one insurance broker at any given time", "Yes, unlimited affiliations are allowed", "Yes, up to 10 companies", "Yes, if registered online"],
        "options_hi": ["नहीं, एक POSP को किसी भी समय केवल एक बीमाकर्ता या एक बीमा ब्रोकर द्वारा नियुक्त किया जा सकता है", "हाँ, असीमित संबद्धता की अनुमति है", "हाँ, 10 कंपनियों तक", "हाँ, यदि ऑनलाइन पंजीकृत है"],
        "correct_index": 0,
        "explanation_en": "IRDAI enforces single affiliation to prevent conflict of interest and cross-selling violations.",
        "explanation_hi": "पीओएसपी केवल एक बीमाकर्ता या एक बीमा ब्रोकर के साथ संबद्ध हो सकता है।",
    },
    {
        "id": "Q-ETH-04",
        "category": "ethics",
        "question_en": "What must a POSP do regarding customer confidentiality and data privacy?",
        "question_hi": "ग्राहक की गोपनीयता और डेटा सुरक्षा के संबंध में एक POSP को क्या करना चाहिए?",
        "options_en": ["Maintain strict confidentiality and never disclose client personal or financial details to third parties", "Share client phone numbers on social media", "Sell client lists to marketing agencies", "Post Aadhaar numbers on public websites"],
        "options_hi": ["कड़ी गोपनीयता बनाए रखें और तीसरे पक्ष को ग्राहक के व्यक्तिगत या वित्तीय विवरण का खुलासा न करें", "सोशल मीडिया पर क्लाइंट फोन नंबर साझा करें", "विपणन एजेंसियों को ग्राहक सूचियां बेचें", "सार्वजनिक वेबसाइटों पर आधार संख्या पोस्ट करें"],
        "correct_index": 0,
        "explanation_en": "POSP code of conduct mandates safeguarding all sensitive personal and financial customer information.",
        "explanation_hi": "पीओएसपी को ग्राहक की सभी व्यक्तिगत और वित्तीय जानकारी को पूरी तरह गोपनीय रखना अनिवार्य है।",
    },
    {
        "id": "Q-ETH-05",
        "category": "ethics",
        "question_en": "What is 'Bima Bharosa' (formerly Integrated Grievance Management System / IGMS)?",
        "question_hi": "'बीमा भरोसा' (पूर्व में IGMS) क्या है?",
        "options_en": ["IRDAI's central portal for registering, tracking, and escalating insurance customer grievances", "A private insurance company", "A bank loan scheme", "A hospital rating website"],
        "options_hi": ["बीमा ग्राहक शिकायतों को दर्ज करने, ट्रैक करने और आगे बढ़ाने के लिए IRDAI का केंद्रीय पोर्टल", "एक निजी बीमा कंपनी", "एक बैंक ऋण योजना", "अस्पताल रेटिंग वेबसाइट"],
        "correct_index": 0,
        "explanation_en": "Bima Bharosa provides an automated central gateway for policyholder complaint redressal.",
        "explanation_hi": "बीमा भरोसा पॉलिसीधारकों की शिकायतों के निवारण के लिए आईआरडीएआई का आधिकारिक पोर्टल है।",
    },
    {
        "id": "Q-ETH-06",
        "category": "ethics",
        "question_en": "What is the maximum claim value that can be entertained by the Insurance Ombudsman?",
        "question_hi": "बीमा लोकपाल (Insurance Ombudsman) द्वारा कितने मूल्य तक के दावों पर विचार किया जा सकता है?",
        "options_en": ["Up to ₹30 Lakhs (inclusive of ex-gratia and other expenses)", "Up to ₹1 Crore", "Up to ₹10,000 only", "Unlimited"],
        "options_hi": ["₹30 लाख तक (अनुग्रह राशि और अन्य खर्चों सहित)", "₹1 करोड़ तक", "केवल ₹10,000 तक", "असीमित"],
        "correct_index": 0,
        "explanation_en": "Under Insurance Ombudsman Rules 2017 (amended), the pecuniary jurisdiction is up to ₹30 Lakhs.",
        "explanation_hi": "बीमा लोकपाल ₹30 लाख तक के व्यक्तिगत दावों और विवादों का निपटारा कर सकता है।",
    },
    {
        "id": "Q-ETH-07",
        "category": "ethics",
        "question_en": "Is a fee charged to the consumer for filing a complaint with the Insurance Ombudsman?",
        "question_hi": "क्या बीमा लोकपाल के पास शिकायत दर्ज करने के लिए उपभोक्ता से कोई शुल्क लिया जाता है?",
        "options_en": ["No, the Insurance Ombudsman service is completely free of cost", "Yes, ₹5,000 court fee", "Yes, 10% of claim amount", "Yes, ₹1,000 registration fee"],
        "options_hi": ["नहीं, बीमा लोकपाल सेवा उपभोक्ताओं के लिए पूरी तरह से निःशुल्क है", "हाँ, ₹5,000 कोर्ट फीस", "हाँ, दावा राशि का 10%", "हाँ, ₹1,000 पंजीकरण शुल्क"],
        "correct_index": 0,
        "explanation_en": "The Ombudsman mechanism is designed as a cost-free, impartial alternative dispute resolution channel.",
        "explanation_hi": "बीमा लोकपाल के समक्ष शिकायत दर्ज करना पूरी तरह निःशुल्क है।",
    },
    {
        "id": "Q-ETH-08",
        "category": "ethics",
        "question_en": "Which of the following is an ethical violation for a POSP during sales?",
        "question_hi": "बिक्री के दौरान POSP के लिए निम्नलिखित में से कौन सा नैतिक उल्लंघन है?",
        "options_en": ["Misrepresenting policy benefits or promising guaranteed returns that do not exist", "Explaining exclusion clauses", "Helping the client fill the proposal accurately", "Checking client identity documents"],
        "options_hi": ["पॉलिसी लाभों का गलत विवरण देना या झूठे गारंटीकृत रिटर्न का वादा करना", "बहिष्करण (Exclusion) खंडों को समझाना", "प्रस्ताव प्रपत्र को सही ढंग से भरने में ग्राहक की मदद करना", "पहचान दस्तावेजों की जांच करना"],
        "correct_index": 0,
        "explanation_en": "Misrepresentation and fraudulent inducement violate core IRDAI market conduct regulations.",
        "explanation_hi": "झूठे वादे करना या लाभों को गलत तरीके से पेश करना गंभीर नैतिक और कानूनी उल्लंघन है।",
    },
    {
        "id": "Q-ETH-09",
        "category": "ethics",
        "question_en": "Can a POSP sign the proposal form on behalf of the customer?",
        "question_hi": "क्या कोई POSP ग्राहक की ओर से प्रस्ताव प्रपत्र (Proposal Form) पर हस्ताक्षर कर सकता है?",
        "options_en": ["No, the proposal form must always be signed or authenticated by the proposer themselves", "Yes, anytime", "Yes, if the customer is busy", "Yes, if authorized verbally"],
        "options_hi": ["नहीं, प्रस्ताव प्रपत्र पर हमेशा प्रस्तावक द्वारा स्वयं हस्ताक्षर या प्रमाणीकरण किया जाना चाहिए", "हाँ, कभी भी", "हाँ, अगर ग्राहक व्यस्त है", "हाँ, अगर मौखिक रूप से अधिकृत है"],
        "correct_index": 0,
        "explanation_en": "Signing on behalf of a customer is forgery and invalidates the contract.",
        "explanation_hi": "ग्राहक के हस्ताक्षर स्वयं करना जालसाजी है और अनुबंध को अमान्य करता है।",
    },
    {
        "id": "Q-ETH-10",
        "category": "ethics",
        "question_en": "What must a POSP disclose to a client before concluding a sale?",
        "question_hi": "बिक्री समाप्त करने से पहले POSP को ग्राहक को क्या खुलासा करना चाहिए?",
        "options_en": ["Their identity, affiliation, commission structure if requested, and all material policy terms & exclusions", "Their personal home address", "Their bank balance", "Their political views"],
        "options_hi": ["अपनी पहचान, संबद्धता, मांगी जाने पर कमीशन संरचना, और पॉलिसी की महत्वपूर्ण शर्तें और बहिष्करण", "उनका व्यक्तिगत घर का पता", "उनका बैंक बैलेंस", "उनके राजनीतिक विचार"],
        "correct_index": 0,
        "explanation_en": "Full transparency regarding identity, products, and exclusions is mandated by IRDAI regulations.",
        "explanation_hi": "पीओएसपी को अपनी पहचान और पॉलिसी की सभी शर्तों और बहिष्करणों का पूर्ण खुलासा करना आवश्यक है।",
    },
]


def seed_question_bank(db) -> int:
    """Seed the default 50 IRDAI questions into exam_question_bank if empty."""
    count = db.execute("SELECT COUNT(*) FROM exam_question_bank").fetchone()[0]
    if count == 0:
        now = int(time.time())
        rows = [
            (
                q["id"],
                q["category"],
                q["question_en"],
                q.get("question_hi"),
                json.dumps(q["options_en"]),
                json.dumps(q.get("options_hi", [])),
                q["correct_index"],
                q.get("explanation_en"),
                q.get("explanation_hi"),
                now,
            )
            for q in DEFAULT_QUESTION_BANK
        ]
        db.executemany(
            """INSERT INTO exam_question_bank (
                id, category, question_en, question_hi, options_en_json,
                options_hi_json, correct_index, explanation_en, explanation_hi, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(rows)
    return 0


def get_exam_eligibility(user: Dict[str, Any], db=None) -> Dict[str, Any]:
    """Check if applicant has completed 15 hours of training and cooldown status."""
    _check_exam_access(user, "exam.start")
    user_id = user["id"]
    now = int(time.time())

    def _eval(conn):
        seed_question_bank(conn)

        app_row = conn.execute(
            "SELECT id, status, stage, details, progress FROM applications WHERE user_id=?",
            (user_id,),
        ).fetchone()

        if not app_row:
            return {"eligible": False, "reason": "APPLICATION_NOT_FOUND"}

        app_status = app_row["status"]

        # Check training completion
        eligible_statuses = {"TRAINING_COMPLETE", "EXAM_ELIGIBLE", "EXAM_FAILED", "EXAM_PASSED", "CERTIFIED"}
        if app_status not in eligible_statuses:
            return {
                "eligible": False,
                "reason": "TRAINING_INCOMPLETE",
                "message": "You must complete the mandatory 15 hours of training before taking the exam.",
            }

        # Check if user has already passed
        if app_status in ("EXAM_PASSED", "CERTIFIED"):
            return {
                "eligible": False,
                "reason": "ALREADY_PASSED",
                "message": "You have already successfully passed the POSP Certification Exam.",
            }

        # Check retake cooldown from last attempt
        last_attempt = conn.execute(
            """SELECT id, passed, completed_at FROM exam_attempts
               WHERE user_id=? ORDER BY started_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()

        if last_attempt and last_attempt["completed_at"] and not last_attempt["passed"]:
            elapsed = now - last_attempt["completed_at"]
            if elapsed < COOLDOWN_SECONDS:
                remaining_secs = COOLDOWN_SECONDS - elapsed
                hours_left = round(remaining_secs / 3600.0, 1)
                return {
                    "eligible": False,
                    "reason": "COOLDOWN_ACTIVE",
                    "retake_available_at": last_attempt["completed_at"] + COOLDOWN_SECONDS,
                    "remaining_seconds": remaining_secs,
                    "hours_remaining": hours_left,
                    "message": f"Retake cooldown active. Next attempt opens in {hours_left} hours.",
                }

        return {
            "eligible": True,
            "reason": "READY",
            "total_questions": TOTAL_QUESTIONS,
            "duration_seconds": EXAM_DURATION_SECONDS,
            "pass_mark_required": PASS_MARK_REQUIRED,
        }

    if db is not None:
        return _eval(db)

    with auth._db() as db_conn:
        return _eval(db_conn)


def start_exam_session(user: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """Start an authoritative exam attempt and return randomized questions without keys."""
    _check_exam_access(user, "exam.start")
    user_id = user["id"]
    now = int(time.time())

    with auth._db() as db:
        seed_question_bank(db)

        # 1. Check if there is an active uncompleted session within time limit to resume
        active_attempt = db.execute(
            """SELECT * FROM exam_attempts
               WHERE user_id=? AND completed_at IS NULL
               ORDER BY started_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()

        if active_attempt and (now - active_attempt["started_at"]) < (active_attempt["duration_seconds"] or 1800):
            # Resume active exam
            q_ids = json.loads(active_attempt["question_ids_json"] or "[]")
            questions = _get_client_questions(db, q_ids, lang)
            rem_secs = max(0, (active_attempt["duration_seconds"] or 1800) - (now - active_attempt["started_at"]))
            return {
                "ok": True,
                "exam_id": active_attempt["id"],
                "attempt_number": active_attempt["attempt_number"],
                "started_at": active_attempt["started_at"],
                "duration_seconds": active_attempt["duration_seconds"],
                "time_remaining_seconds": rem_secs,
                "total_questions": len(questions),
                "questions": questions,
                "resumed": True,
            }

        # 2. Check eligibility with existing connection
        eligibility = get_exam_eligibility(user, db=db)
        if not eligibility["eligible"]:
            raise ValueError(f"ineligible_to_start_exam:{eligibility.get('reason')}")

        # Determine attempt number
        prev_attempts = db.execute("SELECT COUNT(*) FROM exam_attempts WHERE user_id=?", (user_id,)).fetchone()[0]
        attempt_number = prev_attempts + 1

        # Select 50 questions: 10 per category
        categories = ["principles", "general", "life", "health", "ethics"]
        selected_ids = []

        for cat in categories:
            cat_rows = db.execute("SELECT id FROM exam_question_bank WHERE category=?", (cat,)).fetchall()
            cat_ids = [r[0] for r in cat_rows]
            if len(cat_ids) >= 10:
                selected_ids.extend(random.sample(cat_ids, 10))
            else:
                selected_ids.extend(cat_ids)

        # Fallback if less than 50
        if len(selected_ids) < 50:
            remaining_needed = 50 - len(selected_ids)
            more_rows = db.execute("SELECT id FROM exam_question_bank WHERE id NOT IN ({}) LIMIT ?".format(
                ",".join("?" * len(selected_ids)) if selected_ids else "'none'"
            ), (selected_ids + [remaining_needed]) if selected_ids else [remaining_needed]).fetchall()
            selected_ids.extend([r[0] for r in more_rows])

        # Randomize final order
        random.shuffle(selected_ids)

        exam_id = f"EXAM-{user_id}-{attempt_number}-{secrets.token_hex(4)}"

        db.execute(
            """INSERT INTO exam_attempts (
                id, user_id, attempt_number, score, total_questions,
                passed, started_at, completed_at, incident_flag,
                question_ids_json, answers_json, duration_seconds
            ) VALUES (?, ?, ?, 0, ?, 0, ?, NULL, 0, ?, '{}', ?)""",
            (
                exam_id,
                user_id,
                attempt_number,
                len(selected_ids),
                now,
                json.dumps(selected_ids),
                EXAM_DURATION_SECONDS,
            ),
        )

        client_questions = _get_client_questions(db, selected_ids, lang)

    return {
        "ok": True,
        "exam_id": exam_id,
        "attempt_number": attempt_number,
        "started_at": now,
        "duration_seconds": EXAM_DURATION_SECONDS,
        "time_remaining_seconds": EXAM_DURATION_SECONDS,
        "total_questions": len(client_questions),
        "questions": client_questions,
        "pass_mark_required": PASS_MARK_REQUIRED,
        "resumed": False,
    }


def _get_client_questions(db, question_ids: List[str], lang: str) -> List[Dict[str, Any]]:
    """Fetch questions sanitized for candidate display (NO correct_index)."""
    placeholders = ",".join("?" * len(question_ids))
    rows = db.execute(
        f"SELECT id, category, question_en, question_hi, options_en_json, options_hi_json FROM exam_question_bank WHERE id IN ({placeholders})",
        question_ids,
    ).fetchall()

    row_map = {r["id"]: r for r in rows}
    output = []

    for idx, qid in enumerate(question_ids, 1):
        r = row_map.get(qid)
        if not r:
            continue

        q_text = r["question_hi"] if lang == "hi" and r["question_hi"] else r["question_en"]
        opts_raw = r["options_hi_json"] if lang == "hi" and r["options_hi_json"] else r["options_en_json"]
        try:
            options = json.loads(opts_raw or "[]")
        except Exception:
            options = []

        output.append({
            "number": idx,
            "id": r["id"],
            "category": r["category"],
            "question": q_text,
            "options": options,
        })

    return output


def record_exam_incident(
    user: Dict[str, Any],
    exam_id: str,
    incident_type: str,
    details: Optional[str] = None,
) -> Dict[str, Any]:
    """Log candidate proctoring anomaly (tab switch, window blur, multiple faces)."""
    user_id = user["id"]
    with auth._db() as db:
        attempt = db.execute(
            "SELECT id, incident_flag, incident_notes FROM exam_attempts WHERE id=? AND user_id=?",
            (exam_id, user_id),
        ).fetchone()

        if not attempt:
            raise FileNotFoundError("exam_attempt_not_found")

        new_flag = attempt["incident_flag"] + 1
        notes = (attempt["incident_notes"] or "") + f" | [{int(time.time())}] {incident_type}: {details or ''}"

        db.execute(
            "UPDATE exam_attempts SET incident_flag=?, incident_notes=? WHERE id=?",
            (new_flag, notes, exam_id),
        )

    return {"ok": True, "exam_id": exam_id, "incident_recorded": incident_type, "incident_count": new_flag}


def submit_exam_attempt(
    user: Dict[str, Any],
    exam_id: str,
    answers: Dict[str, int],
) -> Dict[str, Any]:
    """Authoritatively score submitted answers against question bank keys."""
    _check_exam_access(user, "exam.submit")
    user_id = user["id"]
    now = int(time.time())

    with auth._db() as db:
        attempt = db.execute(
            "SELECT * FROM exam_attempts WHERE id=? AND user_id=?",
            (exam_id, user_id),
        ).fetchone()

        if not attempt:
            raise FileNotFoundError("exam_attempt_not_found")

        if attempt["completed_at"] is not None:
            raise ValueError("exam_already_completed")

        q_ids = json.loads(attempt["question_ids_json"] or "[]")
        placeholders = ",".join("?" * len(q_ids))
        q_rows = db.execute(
            f"SELECT id, category, correct_index, explanation_en, explanation_hi FROM exam_question_bank WHERE id IN ({placeholders})",
            q_ids,
        ).fetchall()
        key_map = {r["id"]: r for r in q_rows}

        score = 0
        category_breakdown = {}

        for qid in q_ids:
            key_info = key_map.get(qid)
            if not key_info:
                continue

            cat = key_info["category"]
            cat_stats = category_breakdown.setdefault(cat, {"total": 0, "correct": 0})
            cat_stats["total"] += 1

            candidate_ans = answers.get(qid)
            if candidate_ans is not None and int(candidate_ans) == key_info["correct_index"]:
                score += 1
                cat_stats["correct"] += 1

        passed = 1 if score >= PASS_MARK_REQUIRED else 0
        percentage = round((score / float(len(q_ids) or 50)) * 100.0, 1)

        db.execute(
            """UPDATE exam_attempts
               SET score=?, passed=?, completed_at=?, answers_json=?
               WHERE id=?""",
            (score, passed, now, json.dumps(answers or {}), exam_id),
        )

        # Update application status
        app_row = db.execute("SELECT id, progress FROM applications WHERE user_id=?", (user_id,)).fetchone()
        if app_row:
            app_id = app_row["id"]
            progress = json.loads(app_row["progress"] or "{}")
            ex_prog = progress.setdefault("exam", {})
            ex_prog["score"] = score
            ex_prog["passed"] = bool(passed)
            ex_prog["attempts"] = attempt["attempt_number"]
            ex_prog["completed_at"] = now

            if passed:
                # Transition to EXAM_PASSED and stage to Certificate
                db.execute(
                    """UPDATE applications
                       SET status='EXAM_PASSED', stage='Certificate', progress=?, updated_at=?
                       WHERE id=?""",
                    (json.dumps(progress), now, app_id),
                )
                db.execute(
                    "UPDATE cases SET status='EXAM_PASSED', updated_at=? WHERE applicant_id=?",
                    (now, user_id),
                )
                portal.record(db, user_id, "exam_passed", stage="Certificate")
                db.execute(
                    """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
                       VALUES (?, 'success', 'exam_passed', 'Certificate', '', '#certificate', 0, ?, ?)""",
                    (user_id, now, f"PN-{app_id}"),
                )
            else:
                # Transition to EXAM_FAILED with 24h retake cooldown
                ex_prog["retake_at"] = now + COOLDOWN_SECONDS
                db.execute(
                    """UPDATE applications
                       SET status='EXAM_FAILED', progress=?, updated_at=?
                       WHERE id=?""",
                    (json.dumps(progress), now, app_id),
                )
                portal.record(db, user_id, "exam_failed", stage="Exam")
                db.execute(
                    """INSERT INTO notifications (user_id, type, key, stage, doc, action, read, created_at, reference)
                       VALUES (?, 'action', 'exam_failed', 'Exam', '', '#exam', 0, ?, ?)""",
                    (user_id, now, f"PN-{app_id}"),
                )

    return {
        "ok": True,
        "exam_id": exam_id,
        "score": score,
        "total_questions": len(q_ids),
        "percentage": percentage,
        "passed": bool(passed),
        "pass_mark_required": PASS_MARK_REQUIRED,
        "category_breakdown": category_breakdown,
        "retake_cooldown_active": not passed,
        "retake_available_at": (now + COOLDOWN_SECONDS) if not passed else None,
    }


# ------------------------------------------------------------- Exam Admin APIs
def admin_list_attempts(
    actor: Dict[str, Any],
    user_id: Optional[int] = None,
    flagged_only: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List exam sessions with score, status, and proctoring incidents."""
    _check_exam_access(actor, "exam.incident_review")

    query = "SELECT * FROM exam_attempts WHERE 1=1"
    args = []
    if user_id:
        query += " AND user_id=?"
        args.append(user_id)
    if flagged_only:
        query += " AND incident_flag > 0"
    query += " ORDER BY started_at DESC LIMIT ?"
    args.append(max(1, min(limit, 100)))

    with auth._db() as db:
        rows = db.execute(query, args).fetchall()
        return [dict(r) for r in rows]


def admin_override_cooldown(actor: Dict[str, Any], target_user_id: int) -> Dict[str, Any]:
    """Admin endpoint to waive 24h cooldown for verified technical/connectivity glitches."""
    _check_exam_access(actor, "exam.retake_manage")
    now = int(time.time())
    with auth._db() as db:
        # Clear completed_at or set to 25 hours ago on last attempt
        last_att = db.execute(
            "SELECT id FROM exam_attempts WHERE user_id=? ORDER BY started_at DESC LIMIT 1",
            (target_user_id,),
        ).fetchone()

        if last_att:
            db.execute(
                "UPDATE exam_attempts SET completed_at=? WHERE id=?",
                (now - COOLDOWN_SECONDS - 3600, last_att["id"]),
            )

        # Update application status back to TRAINING_COMPLETE / EXAM_ELIGIBLE
        db.execute(
            """UPDATE applications
               SET status='TRAINING_COMPLETE', stage='Exam', updated_at=?
               WHERE user_id=?""",
            (now, target_user_id),
        )

        db.execute(
            """INSERT INTO audit_events (case_id, actor_id, action, occurred)
               VALUES (?, ?, 'EXAM_COOLDOWN_OVERRIDDEN', ?)""",
            (f"user_{target_user_id}", actor["id"], now),
        )

    return {"ok": True, "target_user_id": target_user_id, "cooldown_overridden": True}
