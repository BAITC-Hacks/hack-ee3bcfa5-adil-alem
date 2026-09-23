import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "seed.db"
        self.env = dict(os.environ, DATABASE_URL=f"sqlite:///{self.path}")

    def run_seed(self, *args, expected=0):
        result = subprocess.run([sys.executable, "seed.py", *args],
                                cwd=Path(__file__).resolve().parent, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def snapshot(self):
        with sqlite3.connect(self.path) as db:
            return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                    for table in ("tasks", "teams", "proposals", "demo_seed_records")}

    def test_repeat_and_reset_deterministic(self):
        self.run_seed()
        first = self.snapshot()
        self.assertEqual([len(first[t]) for t in ("tasks", "teams", "proposals")], [8, 5, 9])
        self.run_seed()
        self.assertEqual(first, self.snapshot())
        self.run_seed("--reset")
        self.assertEqual(first, self.snapshot())
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_preserve_edits_and_unrelated_rows(self):
        self.run_seed()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tasks SET title='Edited demo title' WHERE id=1")
            db.execute("INSERT INTO teams (id,name,created_at) VALUES (100,'My real team','2026-09-01')")
        self.run_seed()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT title FROM tasks WHERE id=1").fetchone()[0], "Edited demo title")
        self.run_seed("--reset")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT name FROM teams WHERE id=100").fetchone()[0], "My real team")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM teams").fetchone()[0], 6)

    def test_reset_refuses_external_references_atomically(self):
        self.run_seed()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO proposals (task_id,team_id,solution_idea,status,created_at) VALUES (1,1,'User proposal','pending','2026-09-01')")
        before = self.snapshot()
        result = self.run_seed("--reset", expected=1)
        self.assertIn("Reset refused", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_reset_preserves_interview_history(self):
        self.run_seed()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO interview_sessions (task_id,state,created_at) VALUES (1,'{}','2026-09-01')")
        before = self.snapshot()
        result = self.run_seed("--reset", expected=1)
        self.assertIn("interview history", result.stderr)
        self.assertEqual(before, self.snapshot())
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM interview_sessions").fetchone()[0], 1)
