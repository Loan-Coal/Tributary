"""
Module: models
Layer: ai
Purpose: Pydantic models for AI layer I/O contracts.
Dependencies: typing, pydantic
Used by: ai.client, ai.service, ai.fake_client, tests
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal, Any


class TransactionContext(BaseModel):
    transaction_text: str | None = Field(None, description="Free-form transaction description")
    candidate_jurisdictions: List[str] = Field(default_factory=list, description="ISO country codes")
    model_config = ConfigDict(extra="allow")


class RuleSummary(BaseModel):
    id: str
    summary: str
    as_of_date: str
    source_citation: str


class RuleCitation(BaseModel):
    rule_id: str
    source_citation: str = Field(..., description="Authoritative public source text")
    as_of_date: str = Field(..., description="YYYY-MM-DD of the rule")
    confidence: float = Field(..., ge=0.0, le=1.0)
    taxing_jurisdiction: str = Field(
        default="",
        description="ISO-3166-1 alpha-2 code of the jurisdiction whose tax authority administers this rule",
    )
    reasoning: str = Field(..., description="Why this rule applies")


class AILayerOutput(BaseModel):
    transaction_id: str
    flow_classification: Literal[
        "REVENUE",
        "EXPENSE",
        "INTERCOMPANY",
        "CAPITAL",
        "LOAN",
        "UNCLASSIFIED",
    ]
    candidate_jurisdictions: List[str] = Field(..., description="ISO country codes")
    retrieved_rules: List[RuleCitation]
    evidence_requests: List[str] = Field(..., description="Questions for CPA to satisfy operational tests")
    narrative_template: str = Field(..., description="Must use {{engine:xxx}} placeholders for all numbers")
    needs_human_review: bool
    abstain: bool = Field(..., description="True if info is insufficient to make a determination")
