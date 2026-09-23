from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import stress_test
from ..stress_schemas import StressTestResponse
from .tasks import get_task


router = APIRouter(prefix="/api/tasks/{id}/stress-test", tags=["execution test"])


@router.get("", response_model=StressTestResponse)
def get_stress_test(id: int, db: Session = Depends(get_db)):
    return stress_test.get_stress_test(db, get_task(id, db))


@router.post("", response_model=StressTestResponse)
def run_stress_test(id: int, db: Session = Depends(get_db)):
    return stress_test.run_stress_test(db, get_task(id, db))
