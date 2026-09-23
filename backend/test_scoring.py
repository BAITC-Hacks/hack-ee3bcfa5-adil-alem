import copy
import itertools
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from app import database, models

from app.services.scoring import (
    CATEGORIES, CONFIRMABLE_FIELDS, calculate_score, is_meaningful, readiness_level,
)


FULL_TASK = {
    "context": "The local cafe discards unsold food every evening.",
    "need": "Forecast daily demand to reduce the amount of wasted food.",
    "data": "Daily sales CSV files are available through a shared folder.",
    "expected_result": "A dashboard showing demand predictions for each product.",
    "success_criteria": "Reduce food waste by 20 percent within the first month.",
    "constraints": "Use existing hardware and complete the prototype in two weeks.",
    "users": "Cafe managers and staff responsible for ordering ingredients.",
    "contact": "owner@example.com",
    "interaction_format": "Weekly video calls with the owner and feedback by email.",
}


class ScoringTests(unittest.TestCase):
    def test_step_one_database_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = create_engine(f"sqlite:///{Path(temp) / 'legacy.db'}")
            try:
                with engine.begin() as connection:
                    connection.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, score INTEGER, readiness_level TEXT)"))
                    connection.execute(text("INSERT INTO tasks VALUES (1, 'Existing challenge', 95, 'priority')"))
                with patch.object(database, "engine", engine):
                    database.initialize_database()
                    database.initialize_database()
                with engine.connect() as connection:
                    row = connection.execute(text("SELECT title, score, readiness_level, confirmed_fields FROM tasks")).one()
                    self.assertEqual(tuple(row), ("Existing challenge", 0, "draft", "[]"))
            finally:
                engine.dispose()

    def test_empty(self):
        self.assertEqual(calculate_score({})["score"], 0)

    def test_unconfirmed(self):
        self.assertEqual(calculate_score(FULL_TASK)["score"], 0)

    def test_full(self):
        result = calculate_score(FULL_TASK, CONFIRMABLE_FIELDS)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["recommendations"], [])
        self.assertIsNone(result["next_level"])
        self.assertEqual(result["points_to_next_level"], 0)

    def test_boundaries(self):
        for score, level in [(0, "draft"), (39, "draft"), (40, "working"),
                             (69, "working"), (70, "ready"), (89, "ready"),
                             (90, "priority"), (100, "priority")]:
            with self.subTest(score=score):
                self.assertEqual(readiness_level(score), level)

    def test_partial_categories(self):
        self.assertEqual(calculate_score(FULL_TASK, ["context"])["score"], 10)
        self.assertEqual(calculate_score(FULL_TASK, ["need"])["score"], 10)
        self.assertEqual(calculate_score(FULL_TASK, ["contact"])["score"], 5)
        self.assertEqual(calculate_score(FULL_TASK, ["interaction_format"])["score"], 5)

    def test_short_and_numeric_rules(self):
        for category, fields in CATEGORIES.items():
            for field, maximum in fields.items():
                if field == "contact":
                    continue
                with self.subTest(field=field):
                    result = calculate_score({field: "Short description"}, [field])
                    self.assertEqual(result["score"], maximum // 2)
        task = {"success_criteria": "Staff report a substantial improvement in daily operations."}
        self.assertEqual(calculate_score(task, task)["score"], 7)
        task["success_criteria"] = FULL_TASK["success_criteria"]
        self.assertEqual(calculate_score(task, task)["score"], 15)

    def test_placeholders(self):
        for value in [None, "", "   ", "yes", "no", "none", "test", "n/a", "-", "...",
                      " TEST!!! ", "test test test test", "...............................", "a" * 50]:
            with self.subTest(value=value):
                self.assertFalse(is_meaningful(value, "data"))
                self.assertEqual(calculate_score({"data": value}, ["data"])["score"], 0)

    def test_normalized_length(self):
        self.assertEqual(calculate_score({"data": "  Short    description    "}, ["data"])["score"], 10)
        self.assertFalse(is_meaningful("abc       def", "data"))

    def test_all_confirmation_subsets(self):
        for flags in itertools.product([False, True], repeat=len(CONFIRMABLE_FIELDS)):
            confirmed = [field for field, flag in zip(CONFIRMABLE_FIELDS, flags) if flag]
            result = calculate_score(FULL_TASK, confirmed)
            self.assertLessEqual(result["score"], 100)
            self.assertGreaterEqual(result["score"], 0)
            self.assertEqual(result["score"], sum(c["score"] for c in result["breakdown"].values()))
            self.assertEqual(sum(c["max"] for c in result["breakdown"].values()), 100)
            self.assertTrue(all(0 <= c["score"] <= c["max"] for c in result["breakdown"].values()))
            self.assertEqual(sum(r["potential_gain"] for r in result["recommendations"]), 100 - result["score"])
            self.assertEqual(result["level"], readiness_level(result["score"]))

    def test_pure_and_deterministic(self):
        task = copy.deepcopy(FULL_TASK)
        confirmed = list(CONFIRMABLE_FIELDS)
        before = copy.deepcopy((task, confirmed))
        first = calculate_score(task, confirmed)
        self.assertEqual(first, calculate_score(task, confirmed))
        self.assertEqual((task, confirmed), before)
        self.assertEqual(first, calculate_score(task, confirmed * 3 + ["invalid"]))

    def test_next_level(self):
        for confirmed, score, remaining, level in [([], 0, 40, "working"),
                (["context", "need", "data"], 40, 30, "ready"),
                (["context", "need", "data", "expected_result", "success_criteria"], 70, 20, "priority")]:
            result = calculate_score(FULL_TASK, confirmed)
            self.assertEqual((result["score"], result["points_to_next_level"], result["next_level"]),
                             (score, remaining, level))


if __name__ == "__main__":
    unittest.main()
