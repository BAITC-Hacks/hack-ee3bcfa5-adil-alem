"""Run `python seed.py` or `python seed.py --reset` from backend/."""

import argparse
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, delete, or_, select

from app.database import SessionLocal, engine, initialize_database
from app.models import Proposal, Task, Team, InterviewSession
from app.services.scoring import calculate_score, is_meaningful
from demo_data import TASKS, TEAMS, PROPOSALS


# Local seed ownership ledger; application models and APIs remain unchanged.
ledger_metadata = MetaData()
for model in (Task, Team, Proposal):
    model.__table__.to_metadata(ledger_metadata)
ledger = Table(
    "demo_seed_records", ledger_metadata,
    Column("key", String, primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id")),
    Column("team_id", Integer, ForeignKey("teams.id")),
    Column("proposal_id", Integer, ForeignKey("proposals.id")),
)


def seed_demo(reset=False):
    initialize_database()
    ledger.create(engine, checkfirst=True)
    with SessionLocal.begin() as db:
        records = db.execute(select(ledger)).mappings().all()
        task_ids = [r["task_id"] for r in records if r["task_id"] is not None]
        team_ids = [r["team_id"] for r in records if r["team_id"] is not None]
        proposal_ids = [r["proposal_id"] for r in records if r["proposal_id"] is not None]
        if records and not reset:
            tasks = db.scalars(select(Task).where(Task.id.in_(task_ids)).order_by(Task.id)).all()
            return summary(tasks, len(team_ids), len(proposal_ids), "Existing demo kept")
        if records:
            if db.scalar(select(InterviewSession.task_id).where(InterviewSession.task_id.in_(task_ids)).limit(1)) is not None:
                raise ValueError("Reset refused: demo tasks contain interview history. No data changed.")
            external = db.scalar(select(Proposal.id).where(
                or_(Proposal.task_id.in_(task_ids), Proposal.team_id.in_(team_ids)),
                Proposal.id.not_in(proposal_ids),
            ).limit(1))
            if external is not None:
                raise ValueError("Reset refused: non-demo proposals reference demo tasks or teams. No data changed.")
            db.execute(delete(ledger))
            db.execute(delete(Proposal).where(Proposal.id.in_(proposal_ids)))
            db.execute(delete(Task).where(Task.id.in_(task_ids)))
            db.execute(delete(Team).where(Team.id.in_(team_ids)))

        base_time = datetime(2026, 9, 1, 9)
        tasks, teams = [], []
        for index, fixture in enumerate(TASKS):
            assert all(is_meaningful(fixture.get(f), f) for f in fixture["confirmed_fields"])
            score = calculate_score(fixture, fixture["confirmed_fields"])
            task = Task(**fixture, score=score["score"], readiness_level=score["level"],
                        published=True, created_at=base_time + timedelta(days=index))
            db.add(task)
            db.flush()
            db.execute(ledger.insert().values(key=f"task-{index}", task_id=task.id))
            tasks.append(task)
        for index, fixture in enumerate(TEAMS):
            team = Team(**fixture, created_at=base_time + timedelta(hours=index))
            db.add(team)
            db.flush()
            db.execute(ledger.insert().values(key=f"team-{index}", team_id=team.id))
            teams.append(team)
        for index, (task, team, idea, plan, timeline, status) in enumerate(PROPOSALS):
            proposal = Proposal(
                task_id=tasks[task].id, team_id=teams[team].id, solution_idea=idea,
                plan=plan, timeline=timeline, status=status,
                prototype_url=f"https://example.com/ai-sana-demo/prototype-{index + 1}",
                created_at=base_time + timedelta(days=10, hours=index),
            )
            db.add(proposal)
            db.flush()
            db.execute(ledger.insert().values(key=f"proposal-{index}", proposal_id=proposal.id))
        return summary(tasks, len(teams), len(PROPOSALS), "Demo seeded")


def summary(tasks, teams, proposals, message):
    return {"message": message, "tasks": len(tasks), "teams": teams, "proposals": proposals,
            "levels": dict(Counter(task.readiness_level for task in tasks)),
            "scores": [(task.title, task.score, task.readiness_level) for task in tasks]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace only ledger-owned demo rows; keep unrelated data.")
    args = parser.parse_args()
    try:
        result = seed_demo(reset=args.reset)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(f"{result['message']}: {result['tasks']} tasks, {result['teams']} teams, {result['proposals']} proposals")
    print(f"Readiness distribution: {result['levels']}")
    for title, score, level in result["scores"]:
        print(f"  {score:3} {level:8} {title}")
