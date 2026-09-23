"""Persist original knowledge first; validate AI suggestions before displaying them.

Nothing here writes a Task field, confirmation, publication flag, or score.
"""

from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..interview_schemas import (
    InterviewAIResult, InterviewQuestion, InterviewResponse, InterviewState,
    KnowledgeItem, KnowledgeSource,
)
from ..models import InterviewSession, Task
from . import ai_interviewer


FIELDS = (
    "context", "need", "users", "data", "expected_result", "success_criteria",
    "constraints", "contact", "interaction_format",
)
SAFE_ERROR = "AI returned information that could not be verified. Your information is saved. Please retry."
COMPLETE_REASON = "This interview pass is complete. Review the provided information and revisit unresolved items when more knowledge is available."


def _item(view: InterviewState, field: str) -> KnowledgeItem:
    return next(item for item in view.items if item.field == field)


def _source(view: InterviewState, text: str, role: str, kind: str) -> KnowledgeSource:
    source = KnowledgeSource(id=uuid4().hex, text=text, role=role, kind=kind)
    view.sources.append(source)
    return source


def _read(row: InterviewSession) -> InterviewState:
    return InterviewState.model_validate(row.state["view"])


def _write(row: InterviewSession, view: InterviewState, **internal):
    state = deepcopy(row.state or {})
    state.update(internal)
    state["view"] = view.model_dump(mode="json")
    row.state = state


def _session(db: Session, task: Task) -> InterviewSession:
    row = db.get(InterviewSession, task.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Interview not started")
    return row


def sync_task_knowledge(db: Session, task: Task, fields=()):
    """Called by existing human edit/confirm routes before their transaction commits.

    Supplied fields indicate explicit human edits. With no fields, only reconcile
    confirmation for matching text; never silently accept an AI suggestion.
    """
    row = db.get(InterviewSession, task.id)
    if row is None:
        return
    view = _read(row)
    explicit_fields = set(fields).intersection(FIELDS)
    confirmed = set(task.confirmed_fields or [])
    for item in view.items:
        value = getattr(task, item.field)
        if item.field in explicit_fields:
            if item.value != value or item.status in {"UNKNOWN", "NEEDS_EXPERT", "NOT_APPLICABLE", "CONFLICT"}:
                source = _source(view, value or "", "Business representative", "human_edit")
                item.source = source.id
                item.source_role = source.role
            item.value = value
            item.expert = None
            item.conflicting_source = None
            item.status = "OPEN"
            view.questions = [question for question in view.questions if question.field != item.field]
        if item.status == "CONFLICT":
            item.confirmed = False
        elif item.value == value:
            item.confirmed = item.field in confirmed and bool(value)
            if item.confirmed:
                item.status = "CONFIRMED"
            elif item.status == "CONFIRMED":
                item.status = "OPEN"
        else:
            item.confirmed = False
    pending = row.state.get("pending")
    if pending and pending.get("question", {}).get("field") in explicit_fields:
        # A manual edit supersedes a queued rephrase/verification of old text.
        pending = None
        view.error = None
        if not view.questions and view.status == "active":
            view.status = "paused"
            view.completion_reason = "Your reviewed information is saved. Resume when you want to continue the interview."
    _write(row, view, pending=pending)


def get_interview(db: Session, task: Task) -> InterviewState:
    row = _session(db, task)
    sync_task_knowledge(db, task)
    db.commit()
    return _read(row)


def _eligible(view: InterviewState, answered: list[str]) -> list[str]:
    pending_fields = {question.field for question in view.questions}
    return [
        item.field for item in view.items
        if item.status == "OPEN" and not item.value
        and item.field not in answered and item.field not in pending_fields
    ]


def _payload(task: Task, row: InterviewSession, view: InterviewState, pending: dict) -> dict:
    mode = pending["mode"]
    eligible = _eligible(view, row.state.get("answered", []))
    question = pending.get("question")
    if mode in {"rephrase", "verification"}:
        eligible = [question["field"]]
        count = 1
    elif mode == "extract":
        count = 0
        eligible = []
    else:
        count = min(3, len(eligible))
    return {
        "mode": mode,
        "sources": [source.model_dump() for source in view.sources],
        "items": [item.model_dump() for item in view.items],
        "eligible_fields": eligible,
        "question_count": count,
        "question": question,
        # Deliberately exclude readiness, score, recommendations, and team data.
        "task": {"title": task.title, "industry": task.industry},
    }


def _validate_result(result: InterviewAIResult, payload: dict, view: InterviewState):
    sources = {source.id: source for source in view.sources}
    seen_fields = set()
    for extraction in result.extractions:
        source = sources.get(extraction.source)
        if source is None or source.kind == "action" or not extraction.value.strip() or extraction.value not in source.text:
            raise ValueError("Unsupported extraction")
        if extraction.field in seen_fields:
            raise ValueError("Duplicate extraction")
        seen_fields.add(extraction.field)
        if extraction.conflicting_with is not None:
            earlier = sources.get(extraction.conflicting_with)
            if earlier is None or earlier.kind == "action" or earlier.id == source.id or earlier.text == source.text:
                raise ValueError("Unsupported conflict")
    if payload["mode"] in {"rephrase", "verification"} and result.extractions:
        raise ValueError("A rephrase or verification must not fill answers")
    if payload["mode"] == "rephrase":
        original = " ".join(payload["question"]["text"].casefold().split())
        if any(" ".join(question.text.casefold().split()) == original for question in result.questions):
            raise ValueError("A rephrase must simplify the question, not repeat it")
    remaining_fields = set(payload["eligible_fields"]) - seen_fields
    expected_count = min(payload["question_count"], len(remaining_fields))
    if len(result.questions) != expected_count:
        raise ValueError("Invalid question batch size")
    asked_fields = [question.field for question in result.questions]
    if len(asked_fields) != len(set(asked_fields)) or not set(asked_fields).issubset(remaining_fields):
        raise ValueError("Invalid question targets")
    preserved_questions = view.questions
    if payload["mode"] in {"rephrase", "verification"}:
        preserved_questions = [question for question in view.questions if question.id != payload["question"]["id"]]
    if (sum(question.difficulty == "DEEP" for question in result.questions)
            + sum(question.difficulty == "DEEP" for question in preserved_questions)) > 1:
        raise ValueError("Question batch is too demanding")
    # Prompt handles semantic neutrality; obvious answer menus are also rejected.
    for question in result.questions:
        if not question.text.strip():
            raise ValueError("Empty question")
        lowered = question.text.casefold()
        if any(marker in lowered for marker in ("for example", "e.g.", "choose from", "select one", "a) ", "b) ")):
            raise ValueError("Question suggests answers")


def _generate(db: Session, task: Task, row: InterviewSession) -> InterviewState:
    view = _read(row)
    pending = row.state.get("pending")
    if not pending:
        return view
    payload = _payload(task, row, view, pending)
    original_state = deepcopy(row.state)
    task_id = task.id
    failure = None
    # Release the read transaction while the provider is running. A later human
    # edit/finish must win over this request's older knowledge snapshot.
    db.rollback()
    # No invented fallback questions: only model output may become a question.
    try:
        output = ai_interviewer.generate_interview(payload)
        result = (InterviewAIResult.model_validate_json(output) if isinstance(output, str)
                  else InterviewAIResult.model_validate(output))
        _validate_result(result, payload, view)
    except ai_interviewer.InterviewAIError as exc:
        failure = str(exc)
    except (ValidationError, ValueError, TypeError):
        failure = SAFE_ERROR
    except Exception:
        failure = "AI is temporarily unavailable. Your information is saved. Please retry."

    db.rollback()
    db.expire_all()
    row = db.get(InterviewSession, task_id)
    if row.state != original_state:
        current = _read(row)
        if row.state.get("pending"):
            current.error = "Challenge information changed during analysis. Your latest information is saved. Retry AI to use it."
            _write(row, current)
            db.commit()
        return current
    if failure:
        view.error = failure
        _write(row, view)
        db.commit()
        return view

    sources = {source.id: source for source in view.sources}
    filled_fields = set()
    for extraction in result.extractions:
        item = _item(view, extraction.field)
        if item.status in {"UNKNOWN", "NEEDS_EXPERT", "NOT_APPLICABLE", "CONFLICT"}:
            continue
        # Never replace a confirmed claim without representing the discrepancy.
        if item.confirmed and item.value != extraction.value and extraction.conflicting_with is None:
            continue
        source = sources[extraction.source]
        filled_fields.add(extraction.field)
        item.value = extraction.value
        item.source = source.id
        item.source_role = source.role
        if extraction.conflicting_with is not None:
            item.status = "CONFLICT"
            item.confirmed = False
            item.conflicting_source = extraction.conflicting_with
        elif not item.confirmed:
            item.status = "OPEN"

    # An answer can explicitly supply several facts at once. Do not continue to
    # ask a previously queued question once that information has been provided.
    view.questions = [question for question in view.questions if question.field not in filled_fields]

    if pending["mode"] in {"rephrase", "verification"}:
        original = pending["question"]
        view.questions = [question for question in view.questions if question.id != original["id"]]
    for generated in result.questions:
        item = _item(view, generated.field)
        item.question_difficulty = generated.difficulty
        kind = "clarification"
        if pending["mode"] == "verification":
            kind = "not_applicable_check"
        elif pending["mode"] == "rephrase":
            kind = pending["question"].get("kind", "clarification")
        question = InterviewQuestion(
            id=uuid4().hex, **generated.model_dump(),
            kind=kind,
        )
        view.questions.append(question)
    view.error = None
    view.completion_reason = None
    if not view.questions and not _eligible(view, row.state.get("answered", [])):
        view.status = "complete"
        view.completion_reason = COMPLETE_REASON
    _write(row, view, pending=None)
    db.commit()
    if not view.questions and view.status == "active" and _eligible(view, row.state.get("answered", [])):
        return _continue(db, task, row, view)
    return view


def _continue(db: Session, task: Task, row: InterviewSession, view: InterviewState, *, extract=False):
    eligible = _eligible(view, row.state.get("answered", []))
    if not view.questions and eligible:
        pending = {"mode": "batch"}
    elif extract:
        pending = {"mode": "extract"}
    else:
        pending = None
        if not view.questions:
            view.status = "complete"
            view.completion_reason = COMPLETE_REASON
    _write(row, view, pending=pending)
    db.commit()  # Original answers/status actions survive a provider failure.
    return _generate(db, task, row) if pending else view


def start_interview(db: Session, task: Task) -> InterviewState:
    row = db.get(InterviewSession, task.id)
    if row is not None:
        view = _read(row)
        if view.status == "paused":
            view.status = "active"
            view.completion_reason = None
            _write(row, view)
            db.commit()
            if not row.state.get("pending") and not view.questions:
                return _continue(db, task, row, view)
        # Starting twice never spends credits or overwrites an existing interview.
        return view
    view = InterviewState(task_id=task.id, items=[KnowledgeItem(field=field) for field in FIELDS])
    for item in view.items:
        value = getattr(task, item.field)
        if value is not None and value.strip():
            source = _source(view, value, "Business representative", "task_draft")
            item.value = value
            item.source = source.id
            item.source_role = source.role
            item.confirmed = item.field in (task.confirmed_fields or [])
            item.status = "CONFIRMED" if item.confirmed else "OPEN"
    row = InterviewSession(task_id=task.id, state={})
    db.add(row)
    _write(row, view, answered=[], pending=None)
    return _continue(db, task, row, view)


def respond_interview(db: Session, task: Task, response: InterviewResponse) -> InterviewState:
    row = _session(db, task)
    view = _read(row)
    if view.status != "active":
        raise HTTPException(status_code=409, detail="Resume the interview before answering")
    if row.state.get("pending"):
        raise HTTPException(status_code=409, detail="Retry the saved AI request or finish for now before answering")
    question = next((question for question in view.questions if question.id == response.question_id), None)
    if question is None:
        raise HTTPException(status_code=409, detail="This question has already been handled or is no longer current")
    item = _item(view, question.field)
    role = response.source_role if response.source_role and response.source_role.strip() else "Business representative"
    text = response.answer if response.action == "answer" else response.action
    if response.action == "needs_expert" and response.expert is not None:
        text += ": " + response.expert
    source = _source(view, text, role, "answer" if response.action == "answer" else "action")
    if response.action == "dont_understand" or (response.action == "not_applicable" and question.kind != "not_applicable_check"):
        mode = "rephrase" if response.action == "dont_understand" else "verification"
        _write(row, view, pending={"mode": mode, "question": question.model_dump()})
        db.commit()
        return _generate(db, task, row)

    view.questions = [current for current in view.questions if current.id != question.id]
    answered = list(dict.fromkeys([*row.state.get("answered", []), question.field]))
    _write(row, view, answered=answered)
    if response.action == "dont_know":
        item.status = "UNKNOWN"
    elif response.action == "needs_expert":
        item.status = "NEEDS_EXPERT"
        item.expert = response.expert
    elif response.action == "not_applicable":
        item.status = "NOT_APPLICABLE"
    else:
        # A direct answer is original user knowledge, even if AI is unavailable.
        item.value = response.answer
        item.status = "OPEN"
    item.source = source.id
    item.source_role = source.role
    item.confirmed = False
    if item.status != "OPEN":
        item.value = None
    return _continue(db, task, row, view, extract=response.action == "answer" and item.status == "OPEN")


def retry_interview(db: Session, task: Task) -> InterviewState:
    row = _session(db, task)
    view = _read(row)
    if view.status != "active":
        raise HTTPException(status_code=409, detail="Resume the interview before retrying")
    return _generate(db, task, row)


def finish_interview(db: Session, task: Task) -> InterviewState:
    row = _session(db, task)
    view = _read(row)
    view.status = "paused"
    view.completion_reason = "Finished for now. Your draft, original answers, and unresolved information are saved."
    _write(row, view)
    db.commit()
    return view
