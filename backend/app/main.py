from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, initialize_database
from .routers import proposals, tasks, teams, catalog, interview, stress_test


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield
    engine.dispose()


app = FastAPI(title="AI Sana Challenge Hub", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(tasks.router)
app.include_router(teams.router)
app.include_router(proposals.router)
app.include_router(catalog.router)
app.include_router(interview.router)
app.include_router(stress_test.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
