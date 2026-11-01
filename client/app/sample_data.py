"""Fictional sample policy clauses (INR). Not real government schemes."""
from datetime import date

from .models import CitizenProfile, PolicyClause


def sample_clauses() -> list[PolicyClause]:
    return [
        PolicyClause(
            clause_id="CL-101", scheme_name="MSME Power Tariff Subsidy",
            effective_date=date(2026, 4, 1), category="Financial Grant",
            target_group="Small Business", max_income_limit=250000.0, min_age=21, max_age=60,
            monthly_benefit=2000.0,
            raw_clause="SEC 4(a): Small Business power tariff subsidy of INR 2000/month; max annual income INR 250000; age 21-60.",
        ),
        PolicyClause(
            clause_id="CL-102", scheme_name="Municipal Trade Fee Waiver",
            effective_date=date(2026, 5, 15), category="Tax & Fee Relief",
            target_group="Small Business", max_income_limit=300000.0, min_age=18, max_age=65,
            monthly_benefit=700.0,
            raw_clause="SEC 8(b): Municipal trade license fee waiver worth INR 700/month for Small Business; income cap INR 300000; age 18-65.",
        ),
        PolicyClause(
            clause_id="CL-103", scheme_name="Yuva Skill Stipend",
            effective_date=date(2026, 6, 1), category="Financial Grant",
            target_group="Student", max_income_limit=150000.0, min_age=18, max_age=24,
            monthly_benefit=1500.0,
            raw_clause="NOTIF 12: Monthly stipend of INR 1500 for Students aged 18-24 with family income up to INR 150000.",
        ),
        PolicyClause(
            clause_id="CL-104", scheme_name="Digital Shopkeeper Micro-Credit Rebate",
            effective_date=date(2026, 7, 1), category="Subsidized Loan",
            target_group="Small Business", max_income_limit=200000.0, min_age=21, max_age=55,
            monthly_benefit=1500.0,
            raw_clause="SCHEME 9: Interest rebate of INR 1500/month for Small Business digital adoption; income limit INR 200000; age 21-55.",
        ),
        PolicyClause(
            clause_id="CL-105", scheme_name="Senior Citizen Pension Top-Up",
            effective_date=date(2026, 8, 1), category="Financial Grant",
            target_group="Senior Citizen", max_income_limit=120000.0, min_age=60, max_age=99,
            monthly_benefit=2500.0,
            raw_clause="ORDER 3: Monthly pension top-up of INR 2500 for Senior Citizens aged 60+ with income up to INR 120000.",
        ),
        PolicyClause(
            clause_id="CL-106", scheme_name="Right to 15-Day Deemed Approval",
            effective_date=date(2026, 8, 15), category="Citizen Right", target_group="All",
            monthly_benefit=0.0,
            raw_clause="ACT SEC 14: Universal citizen right; if municipal trade application is not decided in 15 working days, approval is deemed granted.",
        ),
        PolicyClause(
            clause_id="CL-107", scheme_name="Green Packaging Compliance Rule",
            effective_date=date(2026, 9, 1), category="Compliance Rule",
            target_group="Small Business", monthly_benefit=0.0,
            raw_clause="BYLAW 22: Small Business units must ban single-use plastic below 120 microns starting Sept 2026.",
        ),
        PolicyClause(
            clause_id="CL-108", scheme_name="Late Renewal Municipal Penalty",
            effective_date=date(2026, 9, 10), category="Penalty & Fine", target_group="All",
            monthly_benefit=0.0,
            raw_clause="BYLAW 29: Late trade renewal attracts a flat administrative fine; no monthly grant (INR 0).",
        ),
    ]


def default_profile() -> CitizenProfile:
    return CitizenProfile(age=28, annual_income=180000.0, target_group="Small Business", language="Hindi")
