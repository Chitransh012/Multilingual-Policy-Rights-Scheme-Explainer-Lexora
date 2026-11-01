"""Pydantic schemas for Lexora."""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

ClauseCategory = Literal[
    "Financial Grant",
    "Tax & Fee Relief",
    "Subsidized Loan",
    "Citizen Right",
    "Compliance Rule",
    "Penalty & Fine",
    "Healthcare",
    "Other",
]
TargetGroup = Literal[
    "All", "Small Business", "Student", "Senior Citizen", "Woman Entrepreneur", "Worker"
]
Language = Literal["Hindi", "English", "Marathi", "Telugu", "Bengali"]

DEFAULT_GOAL = (
    "Check my eligibility across all loaded clauses, calculate my annual benefit, "
    "and prepare a voice explainer."
)


class PolicyClause(BaseModel):
    clause_id: str = Field(min_length=1, max_length=40)
    scheme_name: str = Field(min_length=1, max_length=120)
    effective_date: date | None = None
    category: ClauseCategory = "Other"
    target_group: TargetGroup = "All"
    max_income_limit: float | None = Field(default=None, ge=0)
    min_age: int | None = Field(default=None, ge=0)
    max_age: int | None = Field(default=None, ge=0)
    monthly_benefit: float = Field(default=0.0, ge=0)
    raw_clause: str | None = None


class PolicyDocument(BaseModel):
    clauses: list[PolicyClause]
    notes: list[str] = Field(default_factory=list)


class CitizenProfile(BaseModel):
    age: int = Field(default=28, ge=1, le=120)
    annual_income: float = Field(default=180000.0, ge=0)
    target_group: TargetGroup = "Small Business"
    language: Language = "Hindi"


class AuditRequest(BaseModel):
    clauses: list[PolicyClause]
    profile: CitizenProfile = Field(default_factory=CitizenProfile)
    goal: str = DEFAULT_GOAL


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = None


class AgentDecision(BaseModel):
    tool_name: Literal[
        "evaluate_eligibility", "calculate_annual_benefit", "generate_voice_explainer", "finish"
    ]
    arguments: str = Field(default="{}", description="Provide arguments as a JSON formatted string")
    message: str = ""


class AuditSession(BaseModel):
    session_id: str
    status: Literal["analyzing", "awaiting_approval", "executing", "done", "failed"] = "analyzing"
    goal: str
    profile: CitizenProfile
    findings: list[str] = Field(default_factory=list)
    pending_action: str | None = None
    audit_log: list[str] = Field(default_factory=list)
    summary: str = ""
    steps: int = 0
