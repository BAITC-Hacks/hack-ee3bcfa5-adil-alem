"""Small, explicit schemas for interview state and structured model output."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


KnowledgeField = Literal[
    "context", "need", "users", "data", "constraints", "expected_result",
    "success_criteria", "contact", "interaction_format",
]
Difficulty = Literal["QUICK", "THINK", "DEEP", "EXPERT"]
KnowledgeStatus = Literal["OPEN", "UNKNOWN", "NEEDS_EXPERT", "NOT_APPLICABLE", "CONFLICT", "CONFIRMED"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeSource(StrictModel):
    id: str
    text: str
    role: str
    kind: str


class KnowledgeItem(StrictModel):
    field: KnowledgeField
    value: str | None = None
    status: KnowledgeStatus = "OPEN"
    source: str | None = None
    source_role: str | None = None
    confirmed: bool = False
    question_difficulty: Difficulty = "THINK"
    expert: str | None = None
    conflicting_source: str | None = None


class InterviewQuestion(StrictModel):
    id: str
    field: KnowledgeField
    text: str
    difficulty: Difficulty
    kind: Literal["clarification", "not_applicable_check"] = "clarification"


class InterviewState(StrictModel):
    task_id: int
    status: Literal["active", "complete", "paused"] = "active"
    items: list[KnowledgeItem]
    sources: list[KnowledgeSource] = Field(default_factory=list)
    questions: list[InterviewQuestion] = Field(default_factory=list)
    error: str | None = None
    completion_reason: str | None = None


class InterviewResponse(StrictModel):
    question_id: str
    action: Literal["answer", "dont_understand", "dont_know", "needs_expert", "not_applicable"]
    answer: str | None = Field(default=None, max_length=12000)
    expert: str | None = Field(default=None, max_length=500)
    source_role: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_answer(self):
        if self.action == "answer" and not (self.answer or "").strip():
            raise ValueError("An answer must not be blank")
        return self


class AIExtraction(StrictModel):
    field: KnowledgeField
    value: str = Field(min_length=1, max_length=12000)
    source: str
    # Both sides must be user sources. This represents a conflict, not its resolution.
    conflicting_with: str | None


class AIQuestion(StrictModel):
    field: KnowledgeField
    text: str = Field(min_length=1, max_length=1200)
    difficulty: Difficulty


class InterviewAIResult(StrictModel):
    extractions: list[AIExtraction] = Field(max_length=18)
    questions: list[AIQuestion] = Field(max_length=3)
    can_finish: bool
