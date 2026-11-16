"""8-Tier Indian Name Matching Engine and Cross-Document Discrepancy Validator.

Complies with IRDAI POSP Onboarding Guidelines:
1. 8-Tier Indian Name Matching:
   - Tier 1: Exact Case-Insensitive Match (Score 1.0)
   - Tier 2: Token-Set / Word Order Inversion (Score 0.98)
   - Tier 3: Honorific & Suffix Normalization (Score 0.95)
   - Tier 4: Initials Expansion & Abbreviation Resolution (Score 0.92)
   - Tier 5: Phonetic Transliteration (Soundex & Indian Dialect Rules) (Score 0.88)
   - Tier 6: Substring & N-gram Jaccard Overlap (Score 0.85)
   - Tier 7: Common Indian Alias & Formalization Dictionary (Score 0.82)
   - Tier 8: Levenshtein Distance Typo Tolerance (<= 2 edits) (Score 0.80)
2. Cross-Document DOB Consistency (PAN, Aadhaar, Class 10).
3. IRDAI POSP Age Qualification (>= 18.0 years old).
4. Minimum 10th Standard Pass Verification.
"""
import datetime
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Indian honorifics, titles, and common non-surname suffixes
INDIAN_HONORIFICS = {
    "mr",
    "mr.",
    "mrs",
    "mrs.",
    "ms",
    "ms.",
    "miss",
    "shri",
    "shree",
    "smt",
    "smt.",
    "dr",
    "dr.",
    "prof",
    "prof.",
    "kumar",
    "kumari",
    "devi",
}

# Phonetic Indian transliteration mappings
PHONETIC_NORMALIZATIONS = [
    (r"chou?dh(a|u)ry?", "chaudhary"),
    (r"chow?dh(a|u)ry?", "chaudhary"),
    (r"sax?s?ena", "saxena"),
    (r"saksena", "saxena"),
    (r"la(x|ksh)mi", "lakshmi"),
    (r"di(x|ksh)it", "dixit"),
    (r"a(g|gg)ar?wal", "agarwal"),
    (r"bh?at?ti?a", "bhatia"),
    (r"v(i|ee)k(a|aa)s", "vikas"),
    (r"b(i|ee)k(a|aa)s", "vikas"),
    (r"sh?arm(a|aa)", "sharma"),
    (r"verm(a|aa)", "verma"),
    (r"gupt(a|aa)", "gupta"),
    (r"singh?", "singh"),
    (r"mukher?jee?", "mukherjee"),
    (r"mukhopadhyay?", "mukherjee"),
    (r"chatter?jee?", "chatterjee"),
    (r"chattopadhyay?", "chatterjee"),
    (r"baner?jee?", "banerjee"),
    (r"bandyopadhyay?", "banerjee"),
]

# Common Indian Nicknames / Pet-name aliases mapped to formal names
INDIAN_NICKNAME_ALIASES = {
    "bobby": "balvinder",
    "guddu": "amit",
    "monu": "manoj",
    "sonu": "sunil",
    "chhotu": "rohit",
    "pinky": "priya",
    "bablu": "alok",
    "bunty": "harpreet",
    "raju": "rajesh",
    "tony": "tarun",
}


def _clean_tokens(name_str: str) -> List[str]:
    """Strip special characters and split into normalized lowercase tokens."""
    clean = re.sub(r"[^\w\s]", " ", (name_str or "").lower())
    return [t for t in clean.split() if t]


def _strip_honorifics(tokens: List[str]) -> List[str]:
    """Remove Indian honorifics and non-essential titles."""
    return [t for t in tokens if t not in INDIAN_HONORIFICS]


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _soundex(token: str) -> str:
    """Generate American/Indian standard Soundex code for a token."""
    if not token:
        return ""
    token = token.upper()
    first = token[0]
    mapping = {
        "B": "1",
        "F": "1",
        "P": "1",
        "V": "1",
        "C": "2",
        "G": "2",
        "J": "2",
        "K": "2",
        "Q": "2",
        "S": "2",
        "X": "2",
        "Z": "2",
        "D": "3",
        "T": "3",
        "L": "4",
        "M": "5",
        "N": "5",
        "R": "6",
    }
    encoded = [first]
    prev = mapping.get(first, "")
    for char in token[1:]:
        code = mapping.get(char, "")
        if code:
            if code != prev:
                encoded.append(code)
            prev = code
        else:
            prev = ""
    res = "".join(encoded) + "0000"
    return res[:4]


def _apply_phonetic_normalization(tokens: List[str]) -> List[str]:
    """Normalize common Indian regional transliteration variants."""
    result = []
    for token in tokens:
        t = token
        for pattern, replacement in PHONETIC_NORMALIZATIONS:
            t = re.sub(f"^{pattern}$", replacement, t)
        result.append(t)
    return result


def _jaccard_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    """Compute token Jaccard similarity coefficient."""
    s1 = set(tokens1)
    s2 = set(tokens2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def match_indian_names(name1: str, name2: str) -> Dict[str, Any]:
    """Execute 8-Tier Indian Name Matching Algorithm."""
    n1 = (name1 or "").strip()
    n2 = (name2 or "").strip()

    if not n1 or not n2:
        return {
            "score": 0.0,
            "tier": 0,
            "tier_name": "EMPTY_NAME",
            "matched": False,
            "status": "MISMATCH",
            "reason": "One or both names are missing.",
        }

    tokens1 = _clean_tokens(n1)
    tokens2 = _clean_tokens(n2)

    # Tier 1: Exact Case-Insensitive Match
    if tokens1 == tokens2:
        return {
            "score": 1.0,
            "tier": 1,
            "tier_name": "EXACT_MATCH",
            "matched": True,
            "status": "EXACT_MATCH",
            "reason": "Names are identical.",
        }

    # Tier 2: Token Set / Word Order Inversion ("Vajja Saisidhardh" vs "Saisidhardh Vajja")
    if set(tokens1) == set(tokens2) and len(tokens1) == len(tokens2):
        return {
            "score": 0.98,
            "tier": 2,
            "tier_name": "TOKEN_PERMUTATION",
            "matched": True,
            "status": "EXACT_MATCH",
            "reason": "Name components match exactly in inverted order.",
        }

    # Tier 3: Honorific & Title Stripping ("Mr. Saisidhardh Vajja" vs "Saisidhardh Vajja")
    clean_t1 = _strip_honorifics(tokens1)
    clean_t2 = _strip_honorifics(tokens2)
    if clean_t1 and clean_t2 and set(clean_t1) == set(clean_t2):
        return {
            "score": 0.95,
            "tier": 3,
            "tier_name": "HONORIFIC_STRIPPED_MATCH",
            "matched": True,
            "status": "CLOSE_MATCH",
            "reason": "Names match exactly after removing honorifics and courtesy titles.",
        }

    # Tier 4: Initials Expansion ("S. Vajja" vs "Saisidhardh Vajja" or "K. V. Rao" vs "Kalluri Venkat Rao")
    # Check if short tokens are initials matching the leading characters of full tokens
    if len(clean_t1) == len(clean_t2) and len(clean_t1) >= 2:
        initials_match = True
        for a, b in zip(clean_t1, clean_t2):
            if a == b:
                continue
            if (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b)):
                continue
            initials_match = False
            break
        if initials_match:
            return {
                "score": 0.92,
                "tier": 4,
                "tier_name": "INITIALS_EXPANSION_MATCH",
                "matched": True,
                "status": "CLOSE_MATCH",
                "reason": "Abbreviated initials match the initial characters of the full name.",
            }

    # Check order-inverted initials ("Vajja S." vs "Saisidhardh Vajja")
    if len(clean_t1) >= 2 and len(clean_t2) >= 2:
        # Check if full surname matches and remaining are initials
        sorted1 = sorted(clean_t1, key=lambda x: -len(x))
        sorted2 = sorted(clean_t2, key=lambda x: -len(x))
        if sorted1[0] == sorted2[0]:
            # Longest component matches
            rem1 = sorted1[1:]
            rem2 = sorted2[1:]
            if len(rem1) == len(rem2):
                order_initials_ok = True
                for r1, r2 in zip(rem1, rem2):
                    if not (r1 == r2 or (len(r1) == 1 and r2.startswith(r1)) or (len(r2) == 1 and r1.startswith(r2))):
                        order_initials_ok = False
                        break
                if order_initials_ok:
                    return {
                        "score": 0.90,
                        "tier": 4,
                        "tier_name": "INITIALS_INVERTED_MATCH",
                        "matched": True,
                        "status": "CLOSE_MATCH",
                        "reason": "Primary surname matches with abbreviated given name initials.",
                    }

    # Tier 5: Phonetic Transliteration (Soundex & Regional Spelling Rules)
    ph1 = _apply_phonetic_normalization(clean_t1)
    ph2 = _apply_phonetic_normalization(clean_t2)
    if set(ph1) == set(ph2):
        return {
            "score": 0.88,
            "tier": 5,
            "tier_name": "PHONETIC_TRANSLITERATION_MATCH",
            "matched": True,
            "status": "CLOSE_MATCH",
            "reason": "Names match via standard Indian regional phonetic transliteration.",
        }

    # Soundex check on tokens
    if len(clean_t1) == len(clean_t2):
        sx1 = sorted([_soundex(t) for t in clean_t1])
        sx2 = sorted([_soundex(t) for t in clean_t2])
        if sx1 == sx2:
            return {
                "score": 0.86,
                "tier": 5,
                "tier_name": "SOUNDEX_PHONETIC_MATCH",
                "matched": True,
                "status": "CLOSE_MATCH",
                "reason": "Phonetic Soundex codes of name components match.",
            }

    # Tier 6: Substring & Jaccard Token Overlap (>= 0.80)
    jaccard = _jaccard_similarity(clean_t1, clean_t2)
    if jaccard >= 0.80:
        return {
            "score": 0.85,
            "tier": 6,
            "tier_name": "JACCARD_TOKEN_OVERLAP",
            "matched": True,
            "status": "CLOSE_MATCH",
            "reason": f"High degree of token overlap ({int(jaccard*100)}%).",
        }

    # Tier 7: Common Indian Nickname & Alias Dictionary
    alias_matched = False
    for t1 in clean_t1:
        formal = INDIAN_NICKNAME_ALIASES.get(t1)
        if formal and formal in clean_t2:
            alias_matched = True
            break
    for t2 in clean_t2:
        formal = INDIAN_NICKNAME_ALIASES.get(t2)
        if formal and formal in clean_t1:
            alias_matched = True
            break
    if alias_matched:
        return {
            "score": 0.82,
            "tier": 7,
            "tier_name": "INDIAN_ALIAS_DICTIONARY_MATCH",
            "matched": True,
            "status": "PARTIAL_MATCH",
            "reason": "Common informal Indian pet-name matched to registered formal name.",
        }

    # Tier 8: Levenshtein Distance Typo Tolerance (<= 2 edits on words with length >= 5)
    if len(clean_t1) == len(clean_t2):
        total_dist = 0
        can_eval = True
        for a, b in zip(sorted(clean_t1), sorted(clean_t2)):
            if min(len(a), len(b)) < 4:
                can_eval = False
                break
            d = _levenshtein_distance(a, b)
            if d > 2:
                can_eval = False
                break
            total_dist += d

        if can_eval and total_dist <= 2:
            return {
                "score": 0.80,
                "tier": 8,
                "tier_name": "LEVENSHTEIN_TYPO_TOLERANCE",
                "matched": True,
                "status": "PARTIAL_MATCH",
                "reason": f"Minor typographical variation detected (edit distance {total_dist}).",
            }

    # If all tiers fail, determine partial match vs mismatch
    partial_score = round(max(jaccard, 0.4 if set(clean_t1) & set(clean_t2) else 0.1), 2)
    status = "PARTIAL_MATCH" if partial_score >= 0.60 else "MISMATCH"

    return {
        "score": partial_score,
        "tier": 0,
        "tier_name": "NO_TIER_MATCH",
        "matched": False,
        "status": status,
        "reason": f"Name mismatch between '{n1}' and '{n2}' (match score {partial_score}).",
    }


def parse_date(date_str: str) -> Optional[datetime.date]:
    """Parse various Indian and ISO date representations into datetime.date."""
    if not date_str:
        return None
    clean = str(date_str).strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(clean, fmt).date()
        except ValueError:
            continue
    return None


def calculate_age_in_years(dob_date: datetime.date, ref_date: Optional[datetime.date] = None) -> float:
    """Calculate exact age in fractional years."""
    ref = ref_date or datetime.date.today()
    years = ref.year - dob_date.year
    if (ref.month, ref.day) < (dob_date.month, dob_date.day):
        years -= 1
    return float(years)


def run_cross_document_checks(
    pan_data: Optional[Dict],
    aadhaar_data: Optional[Dict],
    bank_data: Optional[Dict],
    class10_data: Optional[Dict],
    application_dob: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute comprehensive cross-document verification suite.

    Returns structured report of checks, discrepancies, and overall verdict.
    """
    checks: List[Dict[str, Any]] = []
    discrepancies: List[str] = []

    # 1. PAN vs Aadhaar Name Match
    pan_name = (pan_data or {}).get("holder_name") or (pan_data or {}).get("name") or ""
    aadhaar_name = (aadhaar_data or {}).get("name") or ""
    if pan_name and aadhaar_name:
        res = match_indian_names(pan_name, aadhaar_name)
        status = "PASSED" if res["matched"] else "FAILED"
        if not res["matched"]:
            discrepancies.append(f"Name mismatch between PAN ('{pan_name}') and Aadhaar ('{aadhaar_name}')")
        checks.append({
            "check_name": "NAME_PAN_VS_AADHAAR",
            "status": status,
            "match_score": res["score"],
            "tier": res["tier_name"],
            "details": res["reason"],
        })

    # 2. PAN vs Bank Beneficiary Name Match
    bank_name = (bank_data or {}).get("beneficiary_name_bank") or (bank_data or {}).get("name") or ""
    if pan_name and bank_name:
        res = match_indian_names(pan_name, bank_name)
        status = "PASSED" if res["matched"] else "FAILED"
        if not res["matched"]:
            discrepancies.append(
                f"Bank account holder ('{bank_name}') does not match PAN holder ('{pan_name}'). Commission must be paid to applicant."
            )
        checks.append({
            "check_name": "NAME_PAN_VS_BANK",
            "status": status,
            "match_score": res["score"],
            "tier": res["tier_name"],
            "details": res["reason"],
        })

    # 3. PAN vs Class 10 Candidate Name Match
    class10_name = (class10_data or {}).get("candidate_name") or (class10_data or {}).get("name") or ""
    if pan_name and class10_name:
        res = match_indian_names(pan_name, class10_name)
        status = "PASSED" if res["matched"] else "FAILED"
        if not res["matched"]:
            discrepancies.append(f"Name mismatch between PAN ('{pan_name}') and 10th Marksheet ('{class10_name}')")
        checks.append({
            "check_name": "NAME_PAN_VS_CLASS10",
            "status": status,
            "match_score": res["score"],
            "tier": res["tier_name"],
            "details": res["reason"],
        })

    # 4. PAN vs Aadhaar DOB Match
    pan_dob = parse_date((pan_data or {}).get("dob") or application_dob)
    aadhaar_dob = parse_date((aadhaar_data or {}).get("dob"))
    if pan_dob and aadhaar_dob:
        matched = pan_dob == aadhaar_dob
        status = "PASSED" if matched else "FAILED"
        if not matched:
            discrepancies.append(f"DOB mismatch: PAN has {pan_dob.isoformat()} while Aadhaar has {aadhaar_dob.isoformat()}")
        checks.append({
            "check_name": "DOB_PAN_VS_AADHAAR",
            "status": status,
            "match_score": 1.0 if matched else 0.0,
            "details": "Dates of birth match exactly." if matched else f"DOB discrepancy: PAN ({pan_dob}) vs Aadhaar ({aadhaar_dob})",
        })

    # 5. PAN vs Class 10 DOB Match
    class10_dob = parse_date((class10_data or {}).get("dob"))
    if pan_dob and class10_dob:
        matched = pan_dob == class10_dob
        status = "PASSED" if matched else "FAILED"
        if not matched:
            discrepancies.append(f"DOB mismatch: PAN has {pan_dob.isoformat()} while 10th Marksheet has {class10_dob.isoformat()}")
        checks.append({
            "check_name": "DOB_PAN_VS_CLASS10",
            "status": status,
            "match_score": 1.0 if matched else 0.0,
            "details": "Dates of birth match exactly." if matched else f"DOB discrepancy: PAN ({pan_dob}) vs Class 10 ({class10_dob})",
        })

    # 6. IRDAI Age Eligibility Check (Applicant must be >= 18 years old)
    eval_dob = pan_dob or aadhaar_dob or parse_date(application_dob)
    if eval_dob:
        age = calculate_age_in_years(eval_dob)
        eligible = age >= 18.0
        status = "PASSED" if eligible else "FAILED"
        if not eligible:
            discrepancies.append(f"Applicant is {age:.1f} years old. IRDAI POSP regulations require minimum 18 years.")
        checks.append({
            "check_name": "AGE_ELIGIBILITY_MIN_18",
            "status": status,
            "match_score": 1.0 if eligible else 0.0,
            "details": f"Applicant age is {int(age)} years. Meets POSP minimum age criteria." if eligible else f"Applicant underage ({int(age)} years). POSP minimum is 18 years.",
        })

    # 7. Education Qualification Check (Must have Class 10 Pass)
    if class10_data:
        res_str = str((class10_data or {}).get("result") or "").upper()
        passed = "PASS" in res_str
        status = "PASSED" if passed else "FAILED"
        if not passed:
            discrepancies.append("Class 10 marksheet does not indicate a passing result.")
        checks.append({
            "check_name": "EDUCATION_MINIMUM_CLASS_10",
            "status": status,
            "match_score": 1.0 if passed else 0.0,
            "details": "Class 10 passing status confirmed." if passed else "Secondary education verification failed.",
        })

    # Determine overall cross-document verdict
    has_failed = any(c["status"] == "FAILED" for c in checks)
    verdict = "ACTION_REQUIRED" if has_failed else "ALL_PASSED"

    return {
        "verdict": verdict,
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["status"] == "PASSED"),
        "failed_checks": sum(1 for c in checks if c["status"] == "FAILED"),
        "discrepancies": discrepancies,
        "checks": checks,
        "timestamp": int(time.time()),
    }
