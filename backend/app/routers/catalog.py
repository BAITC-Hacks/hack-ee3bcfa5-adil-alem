from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Task
from ..schemas import TaskRead

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=list[TaskRead])
def catalog(
    sort: Literal["readiness", "newest"] = "readiness",
    industry: str | None = None,
    readiness_level: Literal["draft", "working", "ready", "priority"] | None = None,
    db: Session = Depends(get_db),
):
    query = select(Task).where(Task.published.is_(True))
    if industry is not None:
        query = query.where(Task.industry == industry)
    if readiness_level is not None:
        query = query.where(Task.readiness_level == readiness_level)
    if sort == "readiness":
        query = query.order_by(Task.score.desc())
    return db.scalars(query.order_by(Task.created_at.desc(), Task.id.desc())).all()


@router.get("/{task_id}", response_model=TaskRead)
def catalog_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or not task.published:
        raise HTTPException(status_code=404, detail="Published task not found")
    return task
