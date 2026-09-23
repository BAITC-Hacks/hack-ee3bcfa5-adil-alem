from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..interview_schemas import InterviewResponse, InterviewState
from ..services import interview
from .tasks import get_task


router = APIRouter(prefix="/api/tasks/{id}/interview", tags=["interview"])


@router.get("", response_model=InterviewState)
def get_interview(id: int, db: Session = Depends(get_db)):
    return interview.get_interview(db, get_task(id, db))


@router.post("/start", response_model=InterviewState)
def start_interview(id: int, db: Session = Depends(get_db)):
    return interview.start_interview(db, get_task(id, db))


@router.post("/respond", response_model=InterviewState)
def respond_interview(id: int, payload: InterviewResponse, db: Session = Depends(get_db)):
    return interview.respond_interview(db, get_task(id, db), payload)


@router.post("/retry", response_model=InterviewState)
def retry_interview(id: int, db: Session = Depends(get_db)):
    return interview.retry_interview(db, get_task(id, db))


@router.post("/finish", response_model=InterviewState)
def finish_interview(id: int, db: Session = Depends(get_db)):
    return interview.finish_interview(db, get_task(id, db))
