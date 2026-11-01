"""Lexora FastAPI app: routes, bounded agent loop and in-memory sessions."""
import csv
import io
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from .ai_service import choose_next_step, extract_policy  # noqa: E402
from .models import ApprovalRequest, AuditRequest, AuditSession, PolicyClause  # noqa: E402
from .sample_data import default_profile, sample_clauses  # noqa: E402
from .tools import (  # noqa: E402
    calculate_annual_benefit,
    evaluate_eligibility,
    generate_voice_explainer,
    parse_spoken_query_overrides,
)

MAX_BYTES = 12 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_STEPS = 6
ALLOWLIST = ["evaluate_eligibility", "calculate_annual_benefit", "generate_voice_explainer", "finish"]
SESSIONS: dict[str, AuditSession] = {}

app = FastAPI(title="Lexora - Multilingual Policy, Rights & Scheme Explainer")

_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)


def gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key) and key != "replace_me"


@app.get("/api/health")
def health():
    return {"status": "ok", "gemini_configured": gemini_configured()}


@app.get("/api/sample")
def sample():
    return {
        "clauses": [c.model_dump(mode="json") for c in sample_clauses()],
        "default_profile": default_profile().model_dump(),
        "currency": "INR",
        "source": "fictional civic notification sample",
    }


@app.post("/api/extract")
async def extract(text: str | None = Form(default=None), file: UploadFile | None = File(default=None)):
    trimmed = (text or "").strip()
    has_file = file is not None and bool(file.filename)
    if not trimmed and not has_file:
        raise HTTPException(400, "Paste policy notification text or choose a file.")

    file_bytes: bytes | None = None
    mime = None
    ai_text: str | None = trimmed[:MAX_TEXT_CHARS] or None
    if has_file:
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Please use a file smaller than 12 MB for this demo.")
        if not data:
            raise HTTPException(400, "The selected file is empty.")
        mime = file.content_type or "application/octet-stream"
        if mime == "text/csv" or (file.filename or "").lower().endswith(".csv"):
            try:
                decoded = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise HTTPException(400, "CSV must be UTF-8 encoded.")
            try:
                rows = list(csv.DictReader(io.StringIO(decoded)))
                if not rows:
                    raise ValueError("no data rows found")
            except (csv.Error, ValueError) as e:
                raise HTTPException(400, f"Could not read CSV: {e}")
            ai_text = (
                "CSV rows (extract/normalize only; do not invent values):\n" + repr(rows)
            )[:MAX_TEXT_CHARS]
            file_bytes, mime = None, None
        else:
            file_bytes = data

    try:
        doc = await run_in_threadpool(extract_policy, ai_text, file_bytes, mime)
    except RuntimeError as e:
        if "not configured" in str(e):
            raise HTTPException(503, str(e))
        raise HTTPException(502, f"Gemini extraction failed: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gemini extraction failed: {e}")

    raw_clauses = doc.get("clauses", []) if isinstance(doc, dict) else doc.clauses
    notes = doc.get("notes", []) if isinstance(doc, dict) else doc.notes
    valid: list[dict] = []
    errors: list[dict] = []
    for i, c in enumerate(raw_clauses):
        try:
            raw = c.model_dump() if hasattr(c, "model_dump") else c
            valid.append(PolicyClause.model_validate(raw).model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001
            errors.append({"row": i + 1, "error": str(e)})
    return {"clauses": valid, "notes": list(notes), "validation_errors": errors, "count": len(valid)}


def _log(session: AuditSession, type_: str, message: str, details: dict | None = None) -> None:
    session.audit_log.append(
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": type_,
            "message": message,
            "details": details or {},
        }
    )


def _summary(session: AuditSession) -> str:
    p = session.profile
    if not session.findings:
        return (
            f"No eligible financial schemes matched your citizen profile "
            f"(Age {p.age}, Income INR {p.annual_income:.0f}, Group {p.target_group})."
        )
    calc = calculate_annual_benefit(session.findings)
    return (
        f"Matched {len(session.findings)} eligible scheme(s) ({', '.join(calc['schemes'])}) "
        f"worth INR {calc['total_monthly']:.2f}/month (INR {calc['total_annual']:.2f}/year) in {p.language}."
    )


def run_audit(req: AuditRequest) -> AuditSession:
    effective_profile, overrides = parse_spoken_query_overrides(req.goal, req.profile)
    session = AuditSession(
        session_id=str(uuid.uuid4()), status="analyzing", goal=req.goal, profile=effective_profile
    )
    SESSIONS[session.session_id] = session
    _log(session, "started", "Audit started.",
         {"clause_count": len(req.clauses), "language": effective_profile.language})
    if overrides:
        _log(session, "voice_parsed", "Extracted profile attributes from spoken/text query.", overrides)

    tool_results: list[dict] = []
    try:
        for _ in range(MAX_STEPS):
            session.steps += 1
            decision = choose_next_step(req.goal, session.findings, tool_results, ALLOWLIST)
            tool = decision.tool_name
            _log(session, "plan", decision.message or f"Selected {tool}.",
                 {"tool": tool, "arguments": decision.arguments})
            if tool not in ALLOWLIST:
                raise ValueError("Tool is not allowed")
            if tool == "finish":
                break

            if tool == "evaluate_eligibility":
                session.findings = evaluate_eligibility(req.clauses, session.profile)
                result = session.findings
            elif tool == "calculate_annual_benefit":
                # Always grounded in stored findings; model-supplied numbers are ignored.
                result = (
                    calculate_annual_benefit(session.findings)
                    if session.findings
                    else {"skipped": "No eligible schemes found."}
                )
            else:  # generate_voice_explainer
                if not session.findings:
                    result = {"skipped": "No eligible schemes found."}
                else:
                    calc = calculate_annual_benefit(session.findings)
                    result = generate_voice_explainer(session.findings, session.profile, calc["total_annual"])
                    session.pending_action = {
                        "type": "publish_voice_explainer",
                        "language": session.profile.language,
                        "tts_lang": result["tts_lang"],
                        "scheme_count": calc["scheme_count"],
                        "total_monthly": calc["total_monthly"],
                        "total_annual": calc["total_annual"],
                        "schemes": calc["schemes"],
                        "spoken_summary": result["spoken_summary"],
                        "draft": result["draft"],
                        "dispatched": False,
                    }

            tool_results.append({"tool": tool, "result": result})
            _log(session, "tool", f"Executed {tool}.", {"result": result} if isinstance(result, list) else result)

            if tool == "generate_voice_explainer" and session.pending_action:
                session.status = "awaiting_approval"
                session.summary = _summary(session)
                _log(session, "approval_required",
                     "Voice explainer ready. Waiting for human approval; nothing has been dispatched.")
                return session

        session.status = "done"
        session.summary = _summary(session)
        _log(session, "completed", "Audit completed.", {"steps": session.steps})
    except Exception as e:  # noqa: BLE001
        session.status = "failed"
        session.summary = f"Audit stopped safely: {e}"
        _log(session, "error", str(e))
    return session


@app.post("/api/audits")
def start_audit(req: AuditRequest):
    if not req.clauses:
        raise HTTPException(400, "Add policy clauses before starting an eligibility audit.")
    return run_audit(req).model_dump(mode="json")


def _get_session(session_id: str) -> AuditSession:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(404, "Audit session not found. Start a new audit.")
    return session


@app.get("/api/audits/{session_id}")
def read_audit(session_id: str):
    return _get_session(session_id).model_dump(mode="json")


@app.post("/api/audits/{session_id}/approval")
def decide(session_id: str, req: ApprovalRequest):
    session = _get_session(session_id)
    if session.status != "awaiting_approval" or not session.pending_action:
        raise HTTPException(409, "This audit has no pending approval.")
    pa = session.pending_action
    if req.decision == "approve":
        session.status = "executing"
        pa["simulated_execution"] = (
            "Approved and recorded locally; voice explainer unlocked and no external form was submitted."
        )
        pa["approved"] = True
        _log(session, "approved_simulation", "Human approved the explainer pack (local simulation only).",
             {"language": pa["language"], "reason": req.reason})
        session.status = "done"
        session.summary += " Citizen action pack approved and simulated; no external application was sent."
    else:
        pa["approved"] = False
        _log(session, "rejected", "Human rejected the proposed explainer pack. Nothing was dispatched.",
             {"reason": req.reason})
        session.status = "done"
        session.summary += " Proposed explainer pack rejected; nothing was dispatched."
    pa["dispatched"] = False
    return session.model_dump(mode="json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
