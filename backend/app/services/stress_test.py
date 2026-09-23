"""Plan requirements with AI; evaluate authority without changing business data.

This diagnostic never writes Task or InterviewSession and never invokes scoring.
Quotes validate provenance, not semantic entailment: the model must still identify
the task's relevant requirements and correctly interpret the quoted business text.
"""

from hashlib import sha256
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..interview_schemas import InterviewState
from ..models import InterviewSession, Task, TaskStressTest, utc_now
from ..stress_schemas import (
    ExecutionRequirement, GateResult, StressAIResult, StressResult,
    StressSource, StressTestResponse,
)
from . import ai_interviewer, ai_stress_test


FIELDS = (
    "context", "need", "users", "data", "expected_result", "success_criteria",
    "constraints", "contact", "interaction_format",
)
GATES = ("UNDERSTAND", "START", "ACCESS", "VALIDATE", "DELIVER")
SCOPE_FIELDS = {"context", "need", "expected_result", "constraints"}
SAFE_ERROR = "AI returned an execution test that could not be verified. Your previous result and challenge information are saved. Please retry."
UNAVAILABLE_ERROR = "The execution test is temporarily unavailable. Your previous result and challenge information are saved. Please retry."


def _snapshot(db: Session, task: Task) -> dict:
    """Read relevant inputs only, without starting or synchronizing an interview."""
    row = db.get(InterviewSession, task.id)
    view = InterviewState.model_validate(row.state["view"]) if row else None
    existing = {item.field: item for item in view.items} if view else {}
    confirmed = set(task.confirmed_fields or [])
    items = []
    sources = []
    for field in FIELDS:
        value = getattr(task, field)
        previous = existing.get(field)
        is_confirmed = field in confirmed and bool(value and value.strip())
        status = "CONFIRMED" if is_confirmed else "OPEN"
        item = {
            "field": field, "value": value, "status": status,
            "confirmed": is_confirmed, "source": None, "source_role": None,
            "expert": None, "conflicting_source": None,
        }
        if previous is not None:
            item.update(previous.model_dump(exclude={"question_difficulty"}))
            if previous.status in {"UNKNOWN", "NEEDS_EXPERT", "NOT_APPLICABLE", "CONFLICT"}:
                item["confirmed"] = False
            elif previous.value == value:
                # Explicit Task confirmation is the human authority; never
                # promote a different AI suggestion to confirmed information.
                item["confirmed"] = is_confirmed
                item["status"] = status
            else:
                item["confirmed"] = False
                item["status"] = "OPEN"
            sources.append(StressSource(
                id=f"knowledge:{field}", field=field, text=item["value"],
                kind="knowledge_map", role=item["source_role"],
                knowledge_status=item["status"], confirmed=item["confirmed"],
                expert=item["expert"],
            ).model_dump())
        items.append(item)
        sources.append(StressSource(
            id=f"task:{field}", field=field, text=value, kind="task_field",
            role="Business representative", knowledge_status=status,
            confirmed=is_confirmed, expert=None,
        ).model_dump())
    for field in ("title", "industry"):
        sources.append(StressSource(
            id=f"task:{field}", field=field, text=getattr(task, field),
            kind="task_field", role="Business representative",
            knowledge_status="OPEN", confirmed=False, expert=None,
        ).model_dump())
    if view:
        referenced = {
            reference for item in items
            for reference in (item["source"], item["conflicting_source"])
            if reference
        }
        for source in view.sources:
            # A rephrase action/error/question changes presentation, not business
            # knowledge. Current UNKNOWN/expert/N/A actions do affect the input.
            if source.kind == "action" and source.id not in referenced:
                continue
            sources.append(StressSource(
                id=source.id, field=None, text=source.text, kind=source.kind,
                role=source.role, knowledge_status=None, confirmed=False,
                expert=None,
            ).model_dump())
    return {
        # Prompt/schema corrections must not silently relabel a previous result.
        "analysis_version": 2,
        "task": {"title": task.title, "industry": task.industry},
        "items": items,
        "sources": sorted(sources, key=lambda source: source["id"]),
    }


def _fingerprint(snapshot: dict) -> str:
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _authority(quote, item: dict, sources: dict) -> bool:
    """Only exact evidence in the CURRENT confirmed value can support a pass."""
    if item["status"] != "CONFIRMED" or not item["confirmed"] or not item["value"]:
        return False
    if quote.quote not in item["value"]:
        return False
    if quote.source_ref == f"task:{item['field']}":
        return sources[quote.source_ref]["text"] == item["value"]
    if quote.source_ref == f"knowledge:{item['field']}":
        return True
    return quote.source_ref == item["source"] and sources[quote.source_ref]["kind"] != "action"


def _validate_plan(plan: StressAIResult, snapshot: dict):
    if {requirement.gate for requirement in plan.requirements} != set(GATES):
        raise ValueError("All five execution gates must be covered")
    sources = {source["id"]: source for source in snapshot["sources"]}
    seen = set()
    for requirement in plan.requirements:
        identity = (requirement.gate, requirement.field, requirement.requirement.casefold().strip())
        if identity in seen:
            raise ValueError("Duplicate requirement")
        seen.add(identity)
        if not requirement.requirement.strip() or not requirement.required_information.strip():
            raise ValueError("Empty requirement")
        if any(reference not in sources for reference in requirement.basis_refs):
            raise ValueError("Unknown requirement basis")
        if not any(
            sources[reference]["text"] and sources[reference]["text"].strip()
            and sources[reference]["kind"] != "action"
            for reference in requirement.basis_refs
        ):
            raise ValueError("Missing business basis for a requirement")
        for quote in requirement.evidence:
            source = sources.get(quote.source_ref)
            if (source is None or source["kind"] == "action" or not quote.quote.strip()
                    or not source["text"] or quote.quote not in source["text"]):
                raise ValueError("Unsupported execution evidence")
        # Catch obvious answer menus; semantic neutrality is also a prompt rule.
        question = requirement.required_information.casefold()
        if any(marker in question for marker in ("for example", "e.g.", "choose from", "select one", "a) ", "b) ")):
            raise ValueError("Required information must not suggest answers")


def _evaluate(plan: StressAIResult, snapshot: dict) -> StressResult:
    _validate_plan(plan, snapshot)
    sources = {source["id"]: source for source in snapshot["sources"]}
    items = {item["field"]: item for item in snapshot["items"]}
    requirements = []
    for proposed in plan.requirements:
        item = items[proposed.field]
        knowledge_status = item["status"]
        status = "BLOCKED"
        if knowledge_status == "CONFLICT":
            reason = "Existing business sources conflict. The information required here remains unresolved."
        elif knowledge_status == "UNKNOWN":
            reason = "The business explicitly marked this information as unknown. It has not been supplied."
        elif knowledge_status == "NEEDS_EXPERT":
            reason = "The business marked this information as needing another expert. It remains unresolved."
        elif knowledge_status == "NOT_APPLICABLE":
            if proposed.assessment != "NOT_APPLICABLE":
                # Explicit N/A cannot be treated as either availability or a
                # blocker. Reject inconsistent model interpretation for review.
                raise ValueError("A non-applicable field was treated as required")
            status = "NOT_APPLICABLE"
            reason = "The business explicitly marked this information as not applicable to the challenge."
        elif proposed.assessment == "NOT_APPLICABLE":
            if not proposed.evidence or not all(
                any(_authority(quote, scope, sources) for scope in items.values()
                    if scope["field"] in SCOPE_FIELDS or scope["field"] == proposed.field)
                for quote in proposed.evidence
            ):
                raise ValueError("Non-applicability needs current confirmed scope evidence")
            status = "NOT_APPLICABLE"
            reason = "The quoted, confirmed scope identifies this requirement as unnecessary for this challenge."
        elif knowledge_status != "CONFIRMED":
            reason = ("Business information has been provided, but it has not been human-confirmed."
                      if item["value"] else "The required business information has not been provided or confirmed.")
        elif proposed.assessment in {"SUPPORTED", "UNAVAILABLE"}:
            if not proposed.evidence or not all(_authority(quote, item, sources) for quote in proposed.evidence):
                raise ValueError("This requirement needs evidence from its own current confirmed field")
            if proposed.assessment == "SUPPORTED":
                status = "PASS"
                reason = "Current human-confirmed information supports this requirement. Review the quoted evidence."
            else:
                reason = "Confirmed business information states that this required condition is unavailable or prevents starting. Review the quoted evidence."
        else:
            reason = "The available confirmed information does not establish this specific execution requirement."

        references = list(dict.fromkeys([
            *proposed.basis_refs, *(quote.source_ref for quote in proposed.evidence),
            f"task:{proposed.field}",
            *([f"knowledge:{proposed.field}"] if f"knowledge:{proposed.field}" in sources else []),
            *([item["source"]] if item["source"] in sources else []),
            *([item["conflicting_source"]] if item["conflicting_source"] in sources else []),
        ]))
        requirements.append(ExecutionRequirement(
            gate=proposed.gate, field=proposed.field,
            requirement=proposed.requirement, status=status, reason=reason,
            knowledge_status=knowledge_status, source_refs=references,
            required_information=proposed.required_information,
            expert_if_known=item["expert"] if knowledge_status == "NEEDS_EXPERT" else None,
            evidence=proposed.evidence,
        ))

    gates = []
    for gate in GATES:
        entries = [entry for entry in requirements if entry.gate == gate]
        status = ("BLOCKED" if any(entry.status == "BLOCKED" for entry in entries)
                  else "NOT_APPLICABLE" if all(entry.status == "NOT_APPLICABLE" for entry in entries)
                  else "PASS")
        gates.append(GateResult(gate=gate, status=status, requirements=entries))
    return StressResult(
        created_at=utc_now(), gates=gates,
        gates_passed=sum(gate.status == "PASS" for gate in gates),
        blocker_count=sum(entry.status == "BLOCKED" for entry in requirements),
        sources=[StressSource.model_validate(source) for source in snapshot["sources"]],
    )


def get_stress_test(db: Session, task: Task) -> StressTestResponse:
    row = db.get(TaskStressTest, task.id)
    return StressTestResponse(
        task_id=task.id,
        result=StressResult.model_validate(row.result) if row else None,
        stale=row.input_fingerprint != _fingerprint(_snapshot(db, task)) if row else False,
        error=None,
    )


def _current_task(db: Session, task_id: int) -> Task:
    # End the pre-provider read transaction and reload, so edits made while the
    # request was in flight cannot be hidden by SQLAlchemy's identity map.
    db.rollback()
    db.expire_all()
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def run_stress_test(db: Session, task: Task) -> StressTestResponse:
    task_id = task.id
    snapshot = _snapshot(db, task)
    fingerprint = _fingerprint(snapshot)
    db.rollback()  # Never hold a database transaction across a paid network call.
    try:
        output = ai_stress_test.generate_stress_test(snapshot)
        plan = (StressAIResult.model_validate_json(output) if isinstance(output, str)
                else StressAIResult.model_validate(output))
        result = _evaluate(plan, snapshot)
    except (ValidationError, ValueError, TypeError):
        response = get_stress_test(db, _current_task(db, task_id))
        response.error = SAFE_ERROR
        return response
    except ai_interviewer.InterviewAIError:
        response = get_stress_test(db, _current_task(db, task_id))
        response.error = UNAVAILABLE_ERROR
        return response
    except Exception:
        # Never expose provider exceptions, credentials, headers or request text.
        response = get_stress_test(db, _current_task(db, task_id))
        response.error = UNAVAILABLE_ERROR
        return response

    current = _current_task(db, task_id)
    row = db.get(TaskStressTest, task_id)
    if row is None:
        row = TaskStressTest(task_id=task_id)
        db.add(row)
    row.input_fingerprint = fingerprint
    row.result = result.model_dump(mode="json")
    row.created_at = result.created_at
    db.commit()
    # If relevant knowledge changed during generation, persist the analyzed
    # snapshot as stale. Never claim that an older analysis describes new input.
    return get_stress_test(db, current)
