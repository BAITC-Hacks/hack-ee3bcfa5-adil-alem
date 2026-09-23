from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Literal

from ..database import get_db
from ..models import Proposal, Task, Team
from ..schemas import ProposalCreate, ProposalRead, ProposalUpdate

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def decide_proposal(proposal_id: int, status: Literal["accepted", "rejected"], db: Session):
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal.status = status
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/{proposal_id}/accept", response_model=ProposalRead)
def accept_proposal(proposal_id: int, db: Session = Depends(get_db)):
    return decide_proposal(proposal_id, "accepted", db)


@router.post("/{proposal_id}/reject", response_model=ProposalRead)
def reject_proposal(proposal_id: int, db: Session = Depends(get_db)):
    return decide_proposal(proposal_id, "rejected", db)


def check_references(db: Session, task_id: int, team_id: int):
    if db.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db.get(Team, team_id) is None:
        raise HTTPException(status_code=404, detail="Team not found")


@router.get("", response_model=list[ProposalRead])
def list_proposals(db: Session = Depends(get_db)):
    return db.scalars(select(Proposal).order_by(Proposal.id)).all()


@router.post("", response_model=ProposalRead, status_code=201)
def create_proposal(payload: ProposalCreate, db: Session = Depends(get_db)):
    check_references(db, payload.task_id, payload.team_id)
    proposal = Proposal(**payload.model_dump())
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.patch("/{id}", response_model=ProposalRead)
def update_proposal(id: int, payload: ProposalUpdate, db: Session = Depends(get_db)):
    proposal = db.get(Proposal, id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    changes = payload.model_dump(exclude_unset=True)
    check_references(
        db, changes.get("task_id", proposal.task_id), changes.get("team_id", proposal.team_id)
    )
    for field, value in changes.items():
        setattr(proposal, field, value)
    db.commit()
    db.refresh(proposal)
    return proposal
