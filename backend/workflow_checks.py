"""Step 3 checks called by the live HTTP smoke runner."""

from test_scoring import FULL_TASK


def check_workflow(request):
    created = []
    confirmations = [[], ["context", "need", "data"],
                     ["context", "need", "data", "expected_result", "success_criteria"],
                     list(FULL_TASK)]
    for index, fields in enumerate(confirmations):
        task, _ = request("POST", "/api/tasks", {
            **FULL_TASK, "title": f"Workflow task {index}",
            "industry": "education" if index % 2 == 0 else "retail",
        }, 201)
        path = f"/api/tasks/{task['id']}"
        if fields:
            task, _ = request("POST", path + "/confirm", {"fields": fields})
        assert not task["published"]
        request("GET", f"/api/catalog/{task['id']}", expected=404)
        published, _ = request("POST", path + "/publish")
        assert published["published"] and published["score"] == [0, 40, 70, 100][index]
        created.append(published)
        again, _ = request("POST", path + "/publish")
        assert again == published
        public, _ = request("GET", f"/api/catalog/{task['id']}")
        assert public == published

    for payload in ({"need": "A need"}, {"title": "A title"},
                    {"title": "   ", "need": "A need"}, {"title": "A title", "need": "\t"}):
        task, _ = request("POST", "/api/tasks", payload, 201)
        request("POST", f"/api/tasks/{task['id']}/publish", expected=422)
        request("GET", f"/api/catalog/{task['id']}", expected=404)
        request("POST", "/api/tasks", {**payload, "published": True}, 422)
        request("PATCH", f"/api/tasks/{task['id']}", {"published": True}, 422)

    catalog, _ = request("GET", "/api/catalog")
    assert [t["id"] for t in catalog] == [t["id"] for t in reversed(created)]
    for level in ("draft", "working", "ready", "priority"):
        filtered, _ = request("GET", f"/api/catalog?readiness_level={level}")
        assert len(filtered) == 1 and filtered[0]["readiness_level"] == level
    filtered, _ = request("GET", "/api/catalog?industry=education")
    assert [t["id"] for t in filtered] == [created[2]["id"], created[0]["id"]]
    filtered, _ = request("GET", "/api/catalog?industry=education&readiness_level=ready")
    assert filtered == [created[2]]
    empty, _ = request("GET", "/api/catalog?industry=missing")
    assert empty == []
    newer, _ = request("POST", "/api/tasks", {"title": "Newest draft", "need": "A need", "published": True}, 201)
    newest, _ = request("GET", "/api/catalog?sort=newest")
    assert newest[0]["id"] == newer["id"]
    assert newest == sorted(newest, key=lambda t: (t["created_at"], t["id"]), reverse=True)
    ranked, _ = request("GET", "/api/catalog?sort=readiness")
    assert ranked == sorted(ranked, key=lambda t: (t["score"], t["created_at"], t["id"]), reverse=True)
    assert [t["id"] for t in ranked[-2:]] == [newer["id"], created[0]["id"]]
    request("GET", "/api/catalog?sort=invalid", expected=422)
    request("GET", "/api/catalog?readiness_level=invalid", expected=422)

    path = f"/api/tasks/{created[0]['id']}"
    team, _ = request("POST", "/api/teams", {"name": "Workflow students"}, 201)
    other_team, _ = request("POST", "/api/teams", {"name": "Second students"}, 201)
    submission = {"team_id": team["id"], "solution_idea": "Build a demand dashboard",
                  "plan": "Analyze sales and build a demo", "timeline": "Two weeks",
                  "prototype_url": "https://example.com/demo"}
    for field in submission:
        request("POST", path + "/proposals", {k: v for k, v in submission.items() if k != field}, 422)
    for field in ("solution_idea", "plan", "timeline", "prototype_url"):
        request("POST", path + "/proposals", {**submission, field: "   "}, 422)
    request("POST", path + "/proposals", {**submission, "team_id": 999999}, 404)
    request("POST", path + "/proposals", {**submission, "status": "accepted"}, 422)
    first, _ = request("POST", path + "/proposals", submission, 201)
    second, _ = request("POST", path + "/proposals", {**submission, "team_id": other_team["id"]}, 201)
    third, _ = request("POST", path + "/proposals", submission, 201)
    assert all(p["status"] == "pending" for p in (first, second, third))
    proposals, _ = request("GET", path + "/proposals")
    assert proposals == [first, second, third]
    accepted, _ = request("POST", f"/api/proposals/{first['id']}/accept")
    assert accepted["status"] == "accepted"
    proposals, _ = request("GET", path + "/proposals")
    assert [p["status"] for p in proposals] == ["accepted", "pending", "pending"]
    request("POST", f"/api/proposals/{second['id']}/accept")
    request("POST", f"/api/proposals/{third['id']}/reject")
    proposals, _ = request("GET", path + "/proposals")
    assert [p["status"] for p in proposals] == ["accepted", "accepted", "rejected"]
    again, _ = request("POST", f"/api/proposals/{first['id']}/accept")
    assert again == accepted
    for proposal in (first, second):
        request("POST", f"/api/proposals/{proposal['id']}/reject")
    proposals, _ = request("GET", path + "/proposals")
    assert all(p["status"] == "rejected" for p in proposals)
    request("POST", f"/api/proposals/{first['id']}/accept")
    for payload in ({"title": " "}, {"need": None}):
        request("PATCH", path, payload, 422)
    still_valid, _ = request("GET", path)
    assert still_valid == created[0]
    unpublished, _ = request("POST", path + "/unpublish")
    assert not unpublished["published"]
    again, _ = request("POST", path + "/unpublish")
    assert again == unpublished
    request("POST", path + "/proposals", submission, 409)
    request("GET", f"/api/catalog/{created[0]['id']}", expected=404)
    catalog, _ = request("GET", "/api/catalog")
    assert created[0]["id"] not in [t["id"] for t in catalog]
    retained, _ = request("GET", path + "/proposals")
    assert len(retained) == 3 and retained[0]["status"] == "accepted"
    unrelated, _ = request("GET", f"/api/tasks/{newer['id']}/proposals")
    assert unrelated == []
    for suffix in ("publish", "unpublish"):
        request("POST", f"/api/tasks/999999/{suffix}", expected=404)
    request("GET", "/api/catalog/999999", expected=404)
    request("GET", "/api/tasks/999999/proposals", expected=404)
    request("POST", "/api/tasks/999999/proposals", submission, 404)
    for decision in ("accept", "reject"):
        request("POST", f"/api/proposals/999999/{decision}", expected=404)
    return created[3], first["id"]
