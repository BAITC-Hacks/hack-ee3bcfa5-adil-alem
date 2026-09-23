from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Task, Proposal, Team
from ..schemas import TaskCreate, TaskRead, TaskUpdate, TaskConfirmation, ScoreRead, ProposalSubmission, ProposalRead
from ..services.scoring import CONFIRMABLE_FIELDS, calculate_score, is_meaningful
from ..services.interview import sync_task_knowledge

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def task_score(task: Task):
    return calculate_score(
        {field: getattr(task, field) for field in CONFIRMABLE_FIELDS},
        task.confirmed_fields or [],
    )


def synchronize_score(task: Task):
    result = task_score(task)
    task.score = result["score"]
    task.readiness_level = result["level"]


def validate_publication(task: Task):
    missing = [field for field in ("title", "need") if not (getattr(task, field) or "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail={
            "message": "Publication requires a nonblank title and need", "fields": missing,
        })


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return db.scalars(select(Task).order_by(Task.id)).all()


@router.get("/{id}", response_model=TaskRead)
def get_task(id: int, db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(**payload.model_dump())
    if task.published:
        validate_publication(task)
    synchronize_score(task)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{id}", response_model=TaskRead)
def update_task(id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = get_task(id, db)
    confirmed = set(task.confirmed_fields)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if getattr(task, field) != value:
            confirmed.discard(field)
        setattr(task, field, value)
    task.confirmed_fields = [field for field in CONFIRMABLE_FIELDS if field in confirmed]
    if task.published:
        validate_publication(task)
    synchronize_score(task)
    sync_task_knowledge(db, task, fields=payload.model_fields_set)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{id}/publish", response_model=TaskRead)
def publish_task(id: int, db: Session = Depends(get_db)):
    task = get_task(id, db)
    validate_publication(task)
    task.published = True
    synchronize_score(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{id}/unpublish", response_model=TaskRead)
def unpublish_task(id: int, db: Session = Depends(get_db)):
    task = get_task(id, db)
    task.published = False
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}/proposals", response_model=list[ProposalRead])
def task_proposals(task_id: int, db: Session = Depends(get_db)):
    get_task(task_id, db)
    return db.scalars(select(Proposal).where(Proposal.task_id == task_id).order_by(Proposal.id)).all()


@router.post("/{task_id}/proposals", response_model=ProposalRead, status_code=201)
def submit_proposal(task_id: int, payload: ProposalSubmission, db: Session = Depends(get_db)):
    task = get_task(task_id, db)
    if not task.published:
        raise HTTPException(status_code=409, detail="Task is not published")
    if db.get(Team, payload.team_id) is None:
        raise HTTPException(status_code=404, detail="Team not found")
    proposal = Proposal(task_id=task_id, **payload.model_dump(), status="pending")
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.get("/{id}/score", response_model=ScoreRead)
def get_task_score(id: int, db: Session = Depends(get_db)):
    return task_score(get_task(id, db))


@router.post("/{id}/confirm", response_model=TaskRead)
def confirm_task(id: int, payload: TaskConfirmation, db: Session = Depends(get_db)):
    task = get_task(id, db)
    if payload.confirmed:
        invalid = [field for field in payload.fields if not is_meaningful(getattr(task, field), field)]
        if invalid:
            raise HTTPException(status_code=422, detail={
                "message": "Cannot confirm empty or meaningless fields", "fields": invalid,
            })
    confirmed = set(task.confirmed_fields)
    if payload.confirmed:
        confirmed.update(payload.fields)
    else:
        confirmed.difference_update(payload.fields)
    task.confirmed_fields = [field for field in CONFIRMABLE_FIELDS if field in confirmed]
    synchronize_score(task)
    sync_task_knowledge(db, task)
    db.commit()
    db.refresh(task)
    return task
