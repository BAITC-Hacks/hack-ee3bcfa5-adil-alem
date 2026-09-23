"""Isolated, seeded API for browser tests; never touches the development DB."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

with tempfile.TemporaryDirectory(prefix="sana-browser-") as directory:
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'test.db'}"
    # No real provider request can be authorized by the regression subprocess.
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["OPENAI_MODEL"] = "regression-must-not-call-openai"
    from seed import seed_demo
    from app.database import engine
    from app.services import ai_interviewer, ai_stress_test
    from interview_fixture import generate_interview
    from stress_fixture import generate_stress_test
    import uvicorn

    seed_demo()
    # Patch only the provider boundary: browser tests still exercise real routes,
    # persistence, validation, and scoring, without spending OpenAI credits.
    ai_interviewer.generate_interview = generate_interview
    ai_stress_test.generate_stress_test = generate_stress_test
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
    finally:
        engine.dispose()
