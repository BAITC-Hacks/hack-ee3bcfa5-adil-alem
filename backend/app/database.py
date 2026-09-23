import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parents[1] / 'sana.db'}",
)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine)


def initialize_database():
    Base.metadata.create_all(bind=engine)
    # Small, additive upgrade for existing Step 1 SQLite databases.
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
        if "confirmed_fields" not in columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN confirmed_fields JSON NOT NULL DEFAULT '[]'"))
            # Legacy scores were client-editable; no fields have been confirmed yet.
            connection.execute(text("UPDATE tasks SET score = 0, readiness_level = 'draft'"))


def get_db():
    with SessionLocal() as session:
        yield session
