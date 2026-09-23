"""Run live HTTP checks using a temporary SQLite database and Uvicorn server."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from test_scoring import FULL_TASK
from workflow_checks import check_workflow


def main():
    backend = Path(__file__).resolve().parent
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    checks = 0

    def stop(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            # The Windows venv launcher creates a child Python process.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        else:
            process.terminate()
        process.wait(timeout=10)

    def request(method, path, payload=None, expected=200, headers=None):
        nonlocal checks
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(
            base_url + path, data=body, method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            assert response.status == expected, (method, path, response.status, raw)
            checks += 1
            result = json.loads(raw) if raw and raw[:1] in (b"{", b"[") else raw
            return result, response.headers

    with tempfile.TemporaryDirectory(prefix="sana-smoke-") as temp:
        env = dict(os.environ, DATABASE_URL=f"sqlite:///{Path(temp) / 'test.db'}")
        with open(Path(temp) / "server.log", "w+") as log:
            def start():
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "app.main:app",
                     "--host", "127.0.0.1", "--port", str(port)],
                    cwd=backend, env=env, stdout=log, stderr=log,
                )
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with urlopen(base_url + "/health", timeout=1) as response:
                            if response.status == 200:
                                return process
                    except (URLError, TimeoutError):
                        time.sleep(0.1)
                stop(process)
                raise RuntimeError("Server did not become ready")

            process = start()
            try:
                health, _ = request("GET", "/health")
                assert health == {"status": "ok"}
                request("GET", "/docs")
                request("GET", "/openapi.json")
                task, _ = request("POST", "/api/tasks", {
                    "title": "Reduce food waste", "context": "A local cafe has surplus food."
                }, 201)
                task_id = task["id"]
                assert task["score"] == 0 and task["readiness_level"] == "draft"
                assert task["confirmed"] is False and task["published"] is False
                assert task["need"] is None and task["created_at"]
                fetched, _ = request("GET", f"/api/tasks/{task_id}")
                assert fetched == task
                updated, _ = request("PATCH", f"/api/tasks/{task_id}", {"need": "Forecast demand"})
                assert updated["need"] == "Forecast demand" and updated["title"] == task["title"]
                cleared, _ = request("PATCH", f"/api/tasks/{task_id}", {"context": None})
                assert cleared["context"] is None and cleared["need"] == "Forecast demand"
                unchanged, _ = request("PATCH", f"/api/tasks/{task_id}", {})
                assert unchanged == cleared
                drafts, _ = request("POST", "/api/tasks", {}, 201)
                assert drafts["title"] is None
                tasks, _ = request("GET", "/api/tasks")
                assert len(tasks) == 2
                team, _ = request("POST", "/api/teams", {
                    "name": "Sana Students", "skills": "Python", "technologies": "FastAPI"
                }, 201)
                team_id = team["id"]
                fetched, _ = request("GET", f"/api/teams/{team_id}")
                assert fetched == team
                teams, _ = request("GET", "/api/teams")
                assert teams == [team]
                proposal_body = {"task_id": task_id, "team_id": team_id, "solution_idea": "Demand dashboard"}
                proposal, _ = request("POST", "/api/proposals", proposal_body, 201)
                proposal_id = proposal["id"]
                assert proposal["status"] == "pending"
                proposals, _ = request("GET", "/api/proposals")
                assert proposals == [proposal]
                for status in ("accepted", "rejected"):
                    changed, _ = request("PATCH", f"/api/proposals/{proposal_id}", {"status": status})
                    assert changed["status"] == status and changed["solution_idea"] == proposal["solution_idea"]
                for resource in ("tasks", "teams"):
                    request("GET", f"/api/{resource}/999999", expected=404)
                for resource in ("tasks", "proposals"):
                    request("PATCH", f"/api/{resource}/999999", {}, 404)
                for field in ("task_id", "team_id"):
                    request("POST", "/api/proposals", {**proposal_body, field: 999999}, 404)
                    request("PATCH", f"/api/proposals/{proposal_id}", {field: 999999}, 404)
                request("POST", "/api/teams", {}, 422)
                request("POST", "/api/proposals", {}, 422)
                request("GET", "/api/tasks/not-an-id", expected=422)
                for payload in ({"score": -1}, {"score": 101}, {"confirmed": None}, {"unknown": "x"}):
                    request("POST", "/api/tasks", payload, 422)
                    request("PATCH", f"/api/tasks/{task_id}", payload, 422)
                for payload in ({"status": "invalid"}, {"status": None}, {"task_id": None}, {"team_id": 0}):
                    request("PATCH", f"/api/proposals/{proposal_id}", payload, 422)
                _, headers = request("OPTIONS", "/api/tasks", headers={
                    "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "content-type",
                })
                assert headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
                empty_score, _ = request("GET", f"/api/tasks/{drafts['id']}/score")
                assert empty_score["score"] == 0
                filled, _ = request("POST", "/api/tasks", FULL_TASK, 201)
                scoring_id = filled["id"]
                path = f"/api/tasks/{scoring_id}"
                assert filled["score"] == 0 and filled["confirmed_fields"] == []
                result, _ = request("GET", path + "/score")
                assert result["score"] == 0
                partial, _ = request("POST", path + "/confirm", {"fields": ["context"]})
                assert partial["score"] == 10 and partial["confirmed_fields"] == ["context"]
                complete, _ = request("POST", path + "/confirm", {"fields": list(FULL_TASK)})
                assert complete["score"] == 100 and complete["readiness_level"] == "priority"
                result, _ = request("GET", path + "/score")
                assert result["score"] == sum(c["score"] for c in result["breakdown"].values()) == 100
                assert all(c["score"] <= c["max"] for c in result["breakdown"].values())
                duplicate, _ = request("POST", path + "/confirm", {"fields": ["data", "data"]})
                assert duplicate == complete
                unchanged, _ = request("PATCH", path, {"data": FULL_TASK["data"]})
                assert unchanged == complete
                unrelated, _ = request("PATCH", path, {"title": "A new title"})
                assert unrelated["score"] == 100
                for field in ("score", "title", "published", "not_a_field"):
                    request("POST", path + "/confirm", {"fields": [field]}, 422)
                request("POST", path + "/confirm", {"fields": []}, 422)
                request("POST", f"/api/tasks/{drafts['id']}/confirm", {"fields": ["data"]}, 422)
                edited, _ = request("PATCH", path, {"data": "Updated data files will be shared with student teams."})
                assert edited["score"] == 80 and edited["readiness_level"] == "ready"
                assert "data" not in edited["confirmed_fields"] and "context" in edited["confirmed_fields"]
                request("POST", path + "/confirm", {"fields": ["data"]})
                unconfirmed, _ = request("POST", path + "/confirm", {"fields": ["data"], "confirmed": False})
                assert unconfirmed["score"] == 80 and "data" not in unconfirmed["confirmed_fields"]
                repeated, _ = request("POST", path + "/confirm", {"fields": ["data"], "confirmed": False})
                assert repeated == unconfirmed
                request("PATCH", path, {"data": "test test test"})
                request("POST", path + "/confirm", {"fields": ["data"]}, 422)
                request("POST", path + "/confirm", {"fields": ["data", "context"]}, 422)
                request("PATCH", path, {"data": FULL_TASK["data"]})
                final_scored, _ = request("POST", path + "/confirm", {"fields": ["data"]})
                assert final_scored["score"] == 100
                for payload in ({"score": 50}, {"readiness_level": "priority"}, {"confirmed_fields": ["data"]}):
                    request("POST", "/api/tasks", payload, 422)
                    request("PATCH", path, payload, 422)
                legacy, _ = request("POST", "/api/tasks", {**FULL_TASK, "confirmed": True}, 201)
                assert legacy["score"] == 0
                request("GET", "/api/tasks/999999/score", expected=404)
                request("POST", "/api/tasks/999999/confirm", {"fields": ["data"]}, 404)
                published_task, accepted_proposal_id = check_workflow(request)
                stop(process)
                process = start()
                persisted, _ = request("GET", f"/api/tasks/{task_id}")
                assert persisted == cleared
                persisted, _ = request("GET", "/api/proposals")
                assert persisted[0]["status"] == "rejected"
                assert persisted[0]["task_id"] == task_id
                persisted_score, _ = request("GET", path)
                assert persisted_score == final_scored
                public, _ = request("GET", f"/api/catalog/{published_task['id']}")
                assert public == published_task
                persisted_proposals, _ = request("GET", "/api/proposals")
                assert next(p for p in persisted_proposals if p["id"] == accepted_proposal_id)["status"] == "accepted"
                # Seed the running server's isolated database, preserving prior test data.
                for seed_args in ([], [], ["--reset"]):
                    subprocess.run([sys.executable, "seed.py", *seed_args], cwd=backend,
                                   env=env, check=True, stdout=subprocess.DEVNULL)
                from demo_data import TASKS, TEAMS
                titles = {t["title"] for t in TASKS}
                catalog, _ = request("GET", "/api/catalog")
                demo_tasks = [t for t in catalog if t["title"] in titles]
                assert len(demo_tasks) == 8
                assert {t["readiness_level"] for t in demo_tasks} == {"draft", "working", "ready", "priority"}
                assert demo_tasks == sorted(demo_tasks, key=lambda t: (t["score"], t["created_at"], t["id"]), reverse=True)
                all_teams, _ = request("GET", "/api/teams")
                demo_team_ids = {t["id"] for t in all_teams if t["name"] in {team["name"] for team in TEAMS}}
                assert len(demo_team_ids) == 5
                counts, states = [], set()
                for task in demo_tasks:
                    detail, _ = request("GET", f"/api/catalog/{task['id']}")
                    assert detail == task
                    score, _ = request("GET", f"/api/tasks/{task['id']}/score")
                    assert score["score"] == task["score"] and score["level"] == task["readiness_level"]
                    proposals, _ = request("GET", f"/api/tasks/{task['id']}/proposals")
                    counts.append(len(proposals))
                    for proposal in proposals:
                        assert proposal["task_id"] == task["id"] and proposal["team_id"] in demo_team_ids
                        assert all(proposal[f] for f in ("solution_idea", "plan", "timeline", "prototype_url"))
                        states.add(proposal["status"])
                assert sum(counts) == 9 and max(counts) >= 2 and 0 in counts
                assert states == {"pending", "accepted", "rejected"}
                original, _ = request("GET", f"/api/tasks/{task_id}")
                assert original == cleared
                print(f"PASS: {checks} live HTTP checks, CRUD assertions, CORS, and restart persistence.")
            finally:
                stop(process)


if __name__ == "__main__":
    main()
