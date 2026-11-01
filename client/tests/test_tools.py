import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models import CitizenProfile  # noqa: E402
from app.sample_data import default_profile, sample_clauses  # noqa: E402
from app.tools import (  # noqa: E402
    calculate_annual_benefit,
    evaluate_eligibility,
    generate_voice_explainer,
    parse_spoken_query_overrides,
)

client = TestClient(app)


def _audit_payload(goal="Check my eligibility", profile=None):
    return {
        "clauses": [c.model_dump(mode="json") for c in sample_clauses()],
        "profile": (profile or default_profile()).model_dump(),
        "goal": goal,
    }


def test_sample_eligibility_default_profile():
    findings = evaluate_eligibility(sample_clauses(), default_profile())
    assert [f["clause_id"] for f in findings] == ["CL-101", "CL-102", "CL-104"]


def test_annual_benefit_calculation():
    findings = evaluate_eligibility(sample_clauses(), default_profile())
    calc = calculate_annual_benefit(findings)
    assert calc["total_annual"] == 50400.0
    assert calc["total_monthly"] == 4200.0
    assert calc["scheme_count"] == 3


def test_voice_explainer_all_5_languages():
    findings = evaluate_eligibility(sample_clauses(), default_profile())
    expected = {
        "Hindi": "hi-IN", "English": "en-IN", "Marathi": "mr-IN", "Telugu": "te-IN", "Bengali": "bn-IN",
    }
    for lang, tag in expected.items():
        profile = default_profile().model_copy(update={"language": lang})
        res = generate_voice_explainer(findings, profile, 50400.0)
        assert res["tts_lang"] == tag
        assert res["spoken_summary"].strip()
        assert "4200.00" in res["spoken_summary"] and "50400.00" in res["draft"]
        assert res["dispatched"] is False
    hindi = generate_voice_explainer(findings, default_profile(), 50400.0)
    assert "नमस्ते! लेक्सोरा नीति सहायक में आपका स्वागत है।" in hindi["draft"]


def test_spoken_query_overrides():
    p, o = parse_spoken_query_overrides(
        "I am 20 years old student with income 100000 in Telugu", default_profile()
    )
    assert p.age == 20 and p.annual_income == 100000.0
    assert p.target_group == "Student" and p.language == "Telugu"
    assert set(o) == {"age", "annual_income", "target_group", "language"}


def test_spoken_query_no_overrides():
    p, o = parse_spoken_query_overrides("Tell me about this government scheme", default_profile())
    assert o == {} and p == default_profile()


def test_spoken_query_hindi():
    p, o = parse_spoken_query_overrides(
        "नमस्ते, मेरी उम्र 35 साल है और वार्षिक आय 150000 रुपये है", default_profile()
    )
    assert o == {"age": 35, "annual_income": 150000.0}


def test_high_income_zero_matches():
    profile = CitizenProfile(age=28, annual_income=900000.0, target_group="Small Business")
    assert evaluate_eligibility(sample_clauses(), profile) == []


def test_audit_api_flow_and_double_approval():
    r = client.post("/api/audits", json=_audit_payload())
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "awaiting_approval" and s["steps"] == 3
    assert len(s["findings"]) == 3
    assert s["pending_action"]["total_annual"] == 50400.0
    assert s["pending_action"]["dispatched"] is False
    assert [e["type"] for e in s["audit_log"]] == [
        "started", "plan", "tool", "plan", "tool", "plan", "tool", "approval_required",
    ]
    assert s["summary"] == (
        "Matched 3 eligible scheme(s) (MSME Power Tariff Subsidy, Municipal Trade Fee Waiver, "
        "Digital Shopkeeper Micro-Credit Rebate) worth INR 4200.00/month (INR 50400.00/year) in Hindi."
    )
    sid = s["session_id"]
    ok = client.post(f"/api/audits/{sid}/approval", json={"decision": "approve"})
    assert ok.status_code == 200 and ok.json()["status"] == "done"
    assert ok.json()["pending_action"]["approved"] is True
    assert ok.json()["summary"].endswith("no external application was sent.")
    assert client.post(f"/api/audits/{sid}/approval", json={"decision": "approve"}).status_code == 409
    assert client.get(f"/api/audits/{sid}").status_code == 200


def test_reject_flow():
    sid = client.post("/api/audits", json=_audit_payload()).json()["session_id"]
    r = client.post(f"/api/audits/{sid}/approval", json={"decision": "reject"}).json()
    assert r["pending_action"]["approved"] is False
    assert r["audit_log"][-1]["type"] == "rejected"
    assert r["summary"].endswith("nothing was dispatched.")


def test_spoken_marathi_student_audit():
    s = client.post(
        "/api/audits", json=_audit_payload("I am a 20 years old student with income 100000 in Marathi")
    ).json()
    assert s["profile"]["age"] == 20 and s["profile"]["language"] == "Marathi"
    assert [f["clause_id"] for f in s["findings"]] == ["CL-103"]
    assert s["pending_action"]["tts_lang"] == "mr-IN"
    assert any(e["type"] == "voice_parsed" for e in s["audit_log"])


def test_no_match_audit_is_done():
    payload = _audit_payload()
    payload["profile"]["annual_income"] = 900000
    s = client.post("/api/audits", json=payload).json()
    assert s["status"] == "done" and s["findings"] == [] and s["pending_action"] is None
    assert s["summary"].startswith("No eligible financial schemes matched")


def test_api_errors():
    assert client.post("/api/audits", json={"clauses": [], "profile": {}, "goal": "x"}).status_code == 400
    assert client.post("/api/audits/nope/approval", json={"decision": "approve"}).status_code == 404
    assert client.post("/api/extract").status_code == 400
    r = client.post("/api/extract", data={"text": "CLAUSE 1: something"})
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    empty = client.post("/api/extract", files={"file": ("a.txt", io.BytesIO(b""), "text/plain")})
    assert empty.status_code == 400
    big = client.post(
        "/api/extract", files={"file": ("a.txt", io.BytesIO(b"x" * (13 * 1024 * 1024)), "text/plain")}
    )
    assert big.status_code == 413


def test_health_and_sample():
    assert client.get("/api/health").json()["status"] == "ok"
    s = client.get("/api/sample").json()
    assert len(s["clauses"]) == 8 and s["currency"] == "INR"
