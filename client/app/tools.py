"""Deterministic, read-only tools. None of these contact external services."""
import re

from .models import CitizenProfile, PolicyClause

TTS_LANG = {
    "Hindi": "hi-IN",
    "English": "en-IN",
    "Marathi": "mr-IN",
    "Telugu": "te-IN",
    "Bengali": "bn-IN",
}

_AGE_PATTERNS = [
    re.compile(r"(?i)(?:age|aged|उम्र|आयु|वय|వయస్సు|বয়স)\s*(?:is|है|:)?\s*(\d{1,3})"),
    re.compile(r"(?i)(\d{1,2})\s*(?:years old|साल|वर्ष|वर्षांचे|ఏళ్లు|বছর)"),
]
_INCOME_PATTERN = re.compile(
    r"(?i)(?:income|salary|आय|उत्पन्न|ఆదాయం|আয়)\s*(?:is|of|है|:)?\s*(?:inr|rs\.?|₹)?\s*(\d{4,8})"
)

# Checked in this order; the first group with a matching keyword wins.
_GROUP_KEYWORDS = [
    ("Student", ["student", "छात्र", "विद्यार्थी", "విద్యార్థి", "ছাত্র"]),
    ("Senior Citizen", ["senior", "वरिष्ठ", "वृद्ध", "सीनियर"]),
    ("Woman Entrepreneur", ["woman", "महिला", "महिले"]),
    ("Worker", ["worker", "मजदूर", "कामगार"]),
    ("Small Business", ["small business", "shopkeeper", "व्यापारी", "दुकानदार"]),
]
_LANG_KEYWORDS = [
    ("Hindi", ["in hindi", "हिंदी में"]),
    ("English", ["in english"]),
    ("Marathi", ["in marathi", "मराठीत"]),
    ("Telugu", ["in telugu", "తెలుగులో"]),
    ("Bengali", ["in bengali", "বাংলায়"]),
]


def parse_spoken_query_overrides(goal: str, profile: CitizenProfile) -> tuple[CitizenProfile, dict]:
    """Override profile fields from a spoken/typed query. Form values are the base."""
    overrides: dict = {}
    # "1,80,000" -> "180000" so digit groups with commas are still understood.
    text = re.sub(r"(?<=\d),(?=\d)", "", goal or "")
    lowered = text.lower()

    for pattern in _AGE_PATTERNS:
        m = pattern.search(text)
        if m and 1 <= int(m.group(1)) <= 120:
            overrides["age"] = int(m.group(1))
            break

    m = _INCOME_PATTERN.search(text)
    if m:
        overrides["annual_income"] = float(m.group(1))

    for group, words in _GROUP_KEYWORDS:
        if any(w in lowered for w in words):
            overrides["target_group"] = group
            break

    for lang, words in _LANG_KEYWORDS:
        if any(w in lowered for w in words):
            overrides["language"] = lang
            break

    if not overrides:
        return profile, {}
    return profile.model_copy(update=overrides), overrides


def evaluate_eligibility(clauses: list[PolicyClause], profile: CitizenProfile) -> list[dict]:
    findings: list[dict] = []
    for c in sorted((c for c in clauses if c.monthly_benefit > 0), key=lambda c: c.clause_id):
        if c.target_group != "All" and c.target_group != profile.target_group:
            continue
        if c.max_income_limit is not None and profile.annual_income > c.max_income_limit:
            continue
        if c.min_age is not None and profile.age < c.min_age:
            continue
        if c.max_age is not None and profile.age > c.max_age:
            continue
        findings.append(
            {
                "clause_id": c.clause_id,
                "scheme_name": c.scheme_name,
                "category": c.category,
                "target_group": c.target_group,
                "monthly_benefit": round(c.monthly_benefit, 2),
                "annual_benefit": round(c.monthly_benefit * 12, 2),
                "effective_date": c.effective_date.isoformat() if c.effective_date else None,
                "reason": f"Matches {profile.target_group}, age {profile.age}, income INR {profile.annual_income:.0f}",
            }
        )
    return findings


def calculate_annual_benefit(findings: list[dict]) -> dict:
    if any(f["monthly_benefit"] < 0 for f in findings):
        raise ValueError("Negative monthly benefit is not allowed")
    total_monthly = round(sum(f["monthly_benefit"] for f in findings), 2)
    return {
        "scheme_count": len(findings),
        "total_monthly": total_monthly,
        "total_annual": round(total_monthly * 12, 2),
        "schemes": [f["scheme_name"] for f in findings],
    }


_SCRIPTS = {
    "Hindi": "नमस्ते! लेक्सोरा नीति सहायक में आपका स्वागत है। आपकी प्रोफाइल (आयु {age} वर्ष, वार्षिक आय {income:.0f} रुपये) के आधार पर आप {count} सरकारी योजनाओं के लिए पात्र हैं: {names}। कुल मासिक लाभ {total_monthly:.2f} रुपये और कुल वार्षिक लाभ {total_annual:.2f} रुपये है।",
    "Marathi": "नमस्कार! लेक्सोरा धोरण मार्गदर्शकामध्ये आपले स्वागत आहे. तुमच्या प्रोफाइलनुसार (वय {age} वर्षे, वार्षिक उत्पन्न {income:.0f} रुपये), तुम्ही {count} सरकारी योजनांसाठी पात्र आहात: {names}. एकूण मासिक लाभ {total_monthly:.2f} रुपये आणि वार्षिक लाभ {total_annual:.2f} रुपये आहे.",
    "Telugu": "నమస్కారం! లెక్సోరా పాలసీ గైడ్‌కు స్వాగతం. మీ ప్రొఫైల్ ప్రకారం (వయస్సు {age}, వార్షిక ఆదాయం {income:.0f} రూపాయలు), మీరు {count} ప్రభుత్వ పథకాలకు అర్హులు: {names}. నెలవారీ ప్రయోజనం {total_monthly:.2f} రూపాయలు మరియు వార్షిక ప్రయోజనం {total_annual:.2f} రూపాయలు.",
    "Bengali": "নমস্কার! লেক্সোরা পলিসি গাইডে স্বাগতম। আপনার প্রোফাইল অনুযায়ী (বয়স {age}, বার্ষিক আয় {income:.0f} টাকা), আপনি {count}টি সরকারি প্রকল্পের জন্য যোগ্য: {names}। মোট মাসিক সুবিধা {total_monthly:.2f} টাকা এবং বার্ষিক সুবিধা {total_annual:.2f} টাকা।",
    "English": "Hello! Welcome to your Lexora Policy Explainer. Based on your profile (Age {age}, Annual Income INR {income:.0f}), you qualify for {count} government schemes: {names}. Your combined monthly benefit is INR {total_monthly:.2f} and annual benefit is INR {total_annual:.2f}.",
}


def generate_voice_explainer(findings: list[dict], profile: CitizenProfile, total_annual: float) -> dict:
    """Draft only. Nothing is ever dispatched."""
    names = ", ".join(f["scheme_name"] for f in findings)
    total_monthly = round(total_annual / 12, 2)
    tts_lang = TTS_LANG[profile.language]
    spoken_summary = _SCRIPTS[profile.language].format(
        age=profile.age,
        income=profile.annual_income,
        count=len(findings),
        names=names,
        total_monthly=total_monthly,
        total_annual=total_annual,
    )
    draft = (
        f"[Language: {profile.language} ({tts_lang})]\n"
        f"{spoken_summary}\n\n"
        f"Based on your profile ({profile.target_group}, Age {profile.age}, Income INR {profile.annual_income:.0f}), "
        f"you qualify for {len(findings)} scheme(s): {names}.\n"
        f"Combined Monthly Benefit: INR {total_monthly:.2f}\n"
        f"Combined Annual Impact: INR {total_annual:.2f}\n\n"
        "Action Checklist & Citizen Rights:\n"
        f"1. Gather identity proof, income certificate (<= INR {profile.annual_income:.0f}), and category registration.\n"
        "2. Exercise your Right to 15-Day Deemed Approval on municipal applications.\n"
        "3. Submit at your local citizen facilitation center (CSC) or state portal.\n"
        "4. Confirm final terms in the official notification. This explainer is informational, not legal advice, "
        "and nothing has been submitted on your behalf."
    )
    return {
        "language": profile.language,
        "tts_lang": tts_lang,
        "scheme_count": len(findings),
        "total_monthly": total_monthly,
        "total_annual": round(total_annual, 2),
        "spoken_summary": spoken_summary,
        "draft": draft,
        "dispatched": False,
    }
