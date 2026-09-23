from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class TaskCreate(ApiSchema):
    title: str | None = None
    context: str | None = None
    need: str | None = None
    users: str | None = None
    data: str | None = None
    constraints: str | None = None
    expected_result: str | None = None
    success_criteria: str | None = None
    contact: str | None = None
    interaction_format: str | None = None
    industry: str | None = None
    confirmed: bool = False
    published: bool = False


class TaskUpdate(TaskCreate):
    # All fields are optional to send; routers apply only explicitly sent fields.
    pass


class TaskRead(TaskCreate):
    id: int
    created_at: datetime
    score: int = Field(ge=0, le=100)
    readiness_level: Literal["draft", "working", "ready", "priority"]
    confirmed_fields: list[str]


class TaskConfirmation(ApiSchema):
    fields: list[Literal[
        "context", "need", "users", "data", "constraints", "expected_result",
        "success_criteria", "contact", "interaction_format",
    ]] = Field(min_length=1)
    confirmed: bool = True


class CategoryScore(ApiSchema):
    score: int = Field(ge=0)
    max: int = Field(ge=0)
    missing: list[str]
    reason: str


class ScoreRecommendation(ApiSchema):
    field: str
    potential_gain: int = Field(ge=0)
    message: str


class ScoreRead(ApiSchema):
    score: int = Field(ge=0, le=100)
    level: Literal["draft", "working", "ready", "priority"]
    breakdown: dict[str, CategoryScore]
    missing_fields: list[str]
    recommendations: list[ScoreRecommendation]
    points_to_next_level: int = Field(ge=0)
    next_level: Literal["working", "ready", "priority"] | None


class TeamCreate(ApiSchema):
    name: str = Field(min_length=1)
    interests: str | None = None
    skills: str | None = None
    technologies: str | None = None


class TeamRead(TeamCreate):
    id: int
    created_at: datetime


class ProposalCreate(ApiSchema):
    task_id: int = Field(gt=0)
    team_id: int = Field(gt=0)
    solution_idea: str = Field(min_length=1)
    plan: str | None = None
    timeline: str | None = None
    prototype_url: str | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"


class ProposalUpdate(ApiSchema):
    task_id: int | None = Field(default=None, gt=0)
    team_id: int | None = Field(default=None, gt=0)
    solution_idea: str | None = Field(default=None, min_length=1)
    plan: str | None = None
    timeline: str | None = None
    prototype_url: str | None = None
    status: Literal["pending", "accepted", "rejected"] | None = None

    @field_validator("task_id", "team_id", "solution_idea", "status")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class ProposalRead(ProposalCreate):
    id: int
    created_at: datetime


class ProposalSubmission(ApiSchema):
    team_id: int = Field(gt=0)
    solution_idea: str = Field(min_length=1)
    plan: str = Field(min_length=1)
    timeline: str = Field(min_length=1)
    prototype_url: str = Field(min_length=1)

    @field_validator("solution_idea", "plan", "timeline", "prototype_url")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field must not be blank")
        return value
