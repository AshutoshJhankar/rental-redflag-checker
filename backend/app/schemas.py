"""Contracts: what the LLM must return, and what the API returns."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low"]
Category = Literal[
    "deposit", "lock_in", "notice_period", "rent_escalation", "maintenance_repairs",
    "deductions", "penalties", "termination", "entry_privacy", "usage_restrictions",
    "utilities", "missing_protection", "other",
]
TERM_NAMES = (
    "monthly_rent", "security_deposit", "maintenance_monthly", "agreement_months",
    "lock_in_months", "notice_tenant_months", "notice_landlord_months", "rent_escalation_percent",
)


# ---------- LLM output (validated strictly) ----------

class LLMTerm(BaseModel):
    value: float | None = None
    quote: str | None = Field(default=None, max_length=600)
    clause_id: str | None = None


class LLMFlag(BaseModel):
    category: Category
    severity: Severity
    title: str = Field(min_length=3, max_length=120)
    explanation: str = Field(min_length=10, max_length=600)
    quote: str | None = Field(default=None, max_length=600)
    clause_id: str | None = None
    suggestion: str = Field(min_length=5, max_length=400)


class LLMAnalysis(BaseModel):
    """Top-level shape only. Items are validated one by one so a single bad flag doesn't sink the result."""

    key_terms: dict[str, Any] = Field(default_factory=dict)
    flags: list[Any] = Field(default_factory=list, max_length=25)


# ---------- API output ----------

class KeyTerm(BaseModel):
    value: float | None
    verified: bool
    quote: str | None = None
    clause_id: str | None = None
    page: int | None = None


class Flag(BaseModel):
    category: Category
    severity: Severity
    title: str
    explanation: str
    quote: str | None
    clause_id: str | None
    page: int | None
    suggestion: str
    source: Literal["ai", "rule"]


class Analysis(BaseModel):
    id: str | None = None
    file_name: str
    page_count: int
    clause_count: int
    masked_items: int
    key_terms: dict[str, KeyTerm]
    deposit_months: float | None
    flags: list[Flag]
    risk_score: int
    risk_level: Literal["low", "moderate", "high"]
    discarded_flags: int = 0
    model: str = ""
    created_at: str | None = None
    disclaimer: str = (
        "This is an automated review to help you ask better questions. It is not legal advice. "
        "For anything important, consult a lawyer before signing."
    )
