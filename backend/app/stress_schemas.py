"""Separate execution diagnostics from deterministic readiness scoring."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .interview_schemas import KnowledgeField, KnowledgeStatus, StrictModel


ExecutionGate = Literal["UNDERSTAND", "START", "ACCESS", "VALIDATE", "DELIVER"]
ExecutionStatus = Literal["PASS", "BLOCKED", "NOT_APPLICABLE"]


class SourceQuote(StrictModel):
    source_ref: str = Field(description="Exact existing source ID. task:field and knowledge:field are distinct sources.")
    quote: str = Field(min_length=1, max_length=12000, description="Copy exact source.text only. Never quote null, status/expert metadata, or another source's value.")


class AIExecutionRequirement(StrictModel):
    gate: ExecutionGate
    field: KnowledgeField
    requirement: str = Field(min_length=1, max_length=500)
    required_information: str = Field(min_length=1, max_length=1200)
    # These explain why THIS challenge needs the requirement. Evidence below
    # separately establishes whether the necessary information is available.
    basis_refs: list[str] = Field(min_length=1, max_length=6, description="Existing nonempty business source IDs explaining why this requirement matters. An interview answer may exist in knowledge:need while task:need is null; use the actual source.")
    evidence: list[SourceQuote] = Field(max_length=4, description="Return [] for MISSING. Otherwise quote only relevant current CONFIRMED evidence. Missing values, statuses and action metadata are not quotes.")
    assessment: Literal["SUPPORTED", "MISSING", "UNAVAILABLE", "NOT_APPLICABLE"] = Field(description="Read the target items[field] status first. OPEN, UNKNOWN, NEEDS_EXPERT and CONFLICT mean MISSING, even if text is present. SUPPORTED needs CONFIRMED evidence. N/A needs explicit NOT_APPLICABLE status or confirmed scope proof.")


class StressAIResult(StrictModel):
    requirements: list[AIExecutionRequirement] = Field(min_length=5, max_length=20)


class StressSource(StrictModel):
    id: str
    field: str | None
    text: str | None
    kind: str
    role: str | None
    knowledge_status: KnowledgeStatus | None
    confirmed: bool
    expert: str | None


class ExecutionRequirement(StrictModel):
    gate: ExecutionGate
    field: KnowledgeField
    requirement: str
    status: ExecutionStatus
    reason: str
    knowledge_status: KnowledgeStatus
    source_refs: list[str]
    required_information: str
    expert_if_known: str | None
    evidence: list[SourceQuote]


class GateResult(StrictModel):
    gate: ExecutionGate
    status: ExecutionStatus
    requirements: list[ExecutionRequirement]


class StressResult(StrictModel):
    created_at: datetime
    gates: list[GateResult]
    gates_passed: int = Field(ge=0, le=5)
    blocker_count: int = Field(ge=0)
    sources: list[StressSource]


class StressTestResponse(StrictModel):
    task_id: int
    result: StressResult | None
    stale: bool
    error: str | None
