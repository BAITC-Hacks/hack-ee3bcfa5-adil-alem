"""Execution diagnostics through real routes and SQLite; all AI is mocked."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, main
from app.interview_schemas import InterviewState, KnowledgeItem, KnowledgeSource
from app.models import InterviewSession, Task


FIELDS = {
    "context": "Our Almaty business reviews supplier contracts manually each week.",
    "need": "Review existing supplier contracts to identify clauses requiring attention.",
    "users": "Business contract coordinators will use the review results.",
    "data": "The student team has approved access to 40 anonymized contract documents.",
    "constraints": "The approved contract materials must remain on the company network.",
    "expected_result": "A review report identifying clauses and their document references.",
    "success_criteria": "The contract owner will check the report against 20 reviewed contracts.",
    "contact": "contract-owner@example.com",
    "interaction_format": "The contract owner will answer questions in a weekly online meeting.",
}
GATE_FIELDS = {
    "UNDERSTAND": "need", "START": "context", "ACCESS": "data",
    "VALIDATE": "success_criteria", "DELIVER": "expected_result",
}
REQUIREMENTS = {
    "UNDERSTAND": "The business problem and objective can be understood.",
    "START": "The existing process gives the team a concrete place to begin.",
    "ACCESS": "The information and materials required for this challenge are accessible.",
    "VALIDATE": "The team can identify how the outcome will be evaluated.",
    "DELIVER": "The expected deliverable is sufficiently described.",
}


def model_result(payload, assessments=None):
    """Provider fixture: assessment overrides simulate distinct grounded analyses."""
    assessments = assessments or {}
    sources = {source["id"]: source for source in payload["sources"]}
    requirements = []
    for gate, field in GATE_FIELDS.items():
        source = sources.get(f"task:{field}") or sources.get(f"knowledge:{field}")
        evidence = []
        if source and source["text"]:
            evidence.append({"source_ref": source["id"], "quote": source["text"]})
        basis = f"task:{'need' if gate == 'ACCESS' else field}"
        if basis not in sources or not sources[basis]["text"]:
            basis = "task:need"
        requirements.append({
            "gate": gate, "field": field, "requirement": REQUIREMENTS[gate],
            "required_information": f"Human-confirmed information about {field.replace('_', ' ')}.",
            "basis_refs": [basis], "evidence": evidence,
            "assessment": assessments.get(gate, "SUPPORTED"),
        })
    return {"requirements": requirements}


class StressTestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(temporary.name) / 'execution.db'}",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        self.session_factory = sessionmaker(bind=self.engine)

        def test_database():
            with self.session_factory() as session:
                yield session

        previous = main.app.dependency_overrides.copy()

        def restore_dependencies():
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(previous)

        self.addCleanup(restore_dependencies)
        main.app.dependency_overrides[database.get_db] = test_database
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(database, "engine", self.engine))
        self.stack.enter_context(patch.object(main, "engine", self.engine))
        self.client = self.stack.enter_context(TestClient(main.app))
        self.ai = self.stack.enter_context(patch(
            "app.services.ai_stress_test.generate_stress_test", side_effect=model_result,
        ))

    def task(self, *, confirmed=True, **overrides):
        fields = {**FIELDS, **overrides}
        response = self.client.post("/api/tasks", json={
            "title": "Almaty supplier contract review", "industry": "legal", **fields,
        })
        self.assertEqual(response.status_code, 201, response.text)
        task = response.json()
        if confirmed:
            confirmation = self.client.post(f"/api/tasks/{task['id']}/confirm", json={
                "fields": [field for field, value in fields.items() if field in FIELDS and value],
            })
            self.assertEqual(confirmation.status_code, 200, confirmation.text)
            task = confirmation.json()
        return task

    def current_task(self, task_id):
        response = self.client.get(f"/api/tasks/{task_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def run_test(self, task_id):
        response = self.client.post(f"/api/tasks/{task_id}/stress-test")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def latest(self, task_id):
        response = self.client.get(f"/api/tasks/{task_id}/stress-test")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def item_status(self, task_id, field, status, *, value=None, expert=None):
        """Persist the same original-source shape used by the interview service."""
        task = self.current_task(task_id)
        with self.session_factory() as session:
            row = session.get(InterviewSession, task_id)
            if row:
                state = InterviewState.model_validate(row.state["view"])
            else:
                state = InterviewState(task_id=task_id, items=[
                    KnowledgeItem(field=name, value=task[name],
                                  status="CONFIRMED" if name in task["confirmed_fields"] else "OPEN",
                                  confirmed=name in task["confirmed_fields"])
                    for name in FIELDS
                ])
                row = InterviewSession(task_id=task_id, state={})
                session.add(row)
            item = next(item for item in state.items if item.field == field)
            source_id = f"original-{field}-{len(state.sources)}"
            original = value if value is not None else status.lower()
            if expert is not None:
                original += ": " + expert
            source = KnowledgeSource(id=source_id, text=original,
                                     role="Business owner", kind="answer" if value is not None else "action")
            state.sources.append(source)
            item.value = value
            item.status = status
            item.confirmed = status == "CONFIRMED"
            item.source = source.id
            item.source_role = source.role
            item.expert = expert
            if status == "CONFLICT":
                previous = KnowledgeSource(id=f"previous-{field}", text=task[field] or "Earlier business claim.",
                                           role="Business owner", kind="task_draft")
                state.sources.append(previous)
                item.conflicting_source = previous.id
            row.state = {**row.state, "view": state.model_dump(), "answered": [], "pending": None}
            session.commit()

    @staticmethod
    def gate(state, gate):
        return next(item for item in state["result"]["gates"] if item["gate"] == gate)

    @classmethod
    def requirement(cls, state, gate):
        return cls.gate(state, gate)["requirements"][0]

    def test_complete_confirmed_challenge_passes_five_gates_without_second_score(self):
        task = self.task()
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        self.assertFalse(state["stale"])
        self.assertEqual(state["result"]["gates_passed"], 5)
        self.assertEqual(state["result"]["blocker_count"], 0)
        self.assertEqual({gate["gate"] for gate in state["result"]["gates"]}, set(GATE_FIELDS))
        self.assertTrue(all(gate["status"] == "PASS" for gate in state["result"]["gates"]))
        self.assertEqual(self.current_task(task["id"]), task)

        def no_extra_score(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"score", "confidence", "execution_score", "percentage", "readiness_level"})
                for nested in value.values():
                    no_extra_score(nested)
            elif isinstance(value, list):
                for nested in value:
                    no_extra_score(nested)
        no_extra_score(state)
        no_extra_score(self.ai.call_args.args[0])

    def test_ml_unknown_dataset_access_blocks_without_inventing_data(self):
        task = self.task(need="Predict manufacturing equipment failures from maintenance and sensor records.", data=None)
        self.item_status(task["id"], "data", "UNKNOWN")
        self.ai.side_effect = lambda payload: model_result(payload, {"ACCESS": "MISSING"})
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        requirement = self.requirement(state, "ACCESS")
        self.assertEqual(requirement["status"], "BLOCKED")
        self.assertEqual(requirement["knowledge_status"], "UNKNOWN")
        self.assertIsNone(requirement["expert_if_known"])
        self.assertIsNone(self.current_task(task["id"])["data"])

    def test_dataset_not_applicable_for_explicit_design_scope_is_not_blocker(self):
        task = self.task(context="The team will design a public information page; no existing dataset or private records are needed.", data=None)

        def design_scope(payload):
            result = model_result(payload, {"ACCESS": "NOT_APPLICABLE"})
            access = next(row for row in result["requirements"] if row["gate"] == "ACCESS")
            context = next(source for source in payload["sources"] if source["id"] == "task:context")
            access["basis_refs"] = ["task:context"]
            access["evidence"] = [{"source_ref": "task:context", "quote": context["text"]}]
            return result

        self.ai.side_effect = design_scope
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        self.assertEqual(self.gate(state, "ACCESS")["status"], "NOT_APPLICABLE")
        self.assertEqual(state["result"]["blocker_count"], 0)
        self.assertEqual(state["result"]["gates_passed"], 4)

    def test_missing_validation_and_deliverable_are_specific_blockers(self):
        task = self.task(success_criteria=None, expected_result=None)
        self.ai.side_effect = lambda payload: model_result(payload, {"VALIDATE": "MISSING", "DELIVER": "MISSING"})
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        self.assertEqual(self.gate(state, "VALIDATE")["status"], "BLOCKED")
        self.assertEqual(self.gate(state, "DELIVER")["status"], "BLOCKED")
        self.assertEqual(state["result"]["blocker_count"], 2)
        for gate in ("VALIDATE", "DELIVER"):
            self.assertTrue(self.requirement(state, gate)["required_information"])
            self.assertTrue(self.requirement(state, gate)["source_refs"])

    def test_needs_expert_displays_exact_user_role_only(self):
        for expert in ("IT department — Aigerim", None):
            with self.subTest(expert=expert):
                task = self.task(data=None)
                self.item_status(task["id"], "data", "NEEDS_EXPERT", expert=expert)
                state = self.run_test(task["id"])
                self.assertIsNone(state["error"])
                requirement = self.requirement(state, "ACCESS")
                self.assertEqual(requirement["status"], "BLOCKED")
                self.assertEqual(requirement["knowledge_status"], "NEEDS_EXPERT")
                self.assertEqual(requirement["expert_if_known"], expert)

    def test_unresolved_knowledge_never_becomes_pass_even_with_old_confirmed_task(self):
        for status in ("UNKNOWN", "OPEN", "CONFLICT"):
            with self.subTest(status=status):
                task = self.task()
                self.item_status(task["id"], "data", status, value="Access is disputed and has not been settled." if status != "UNKNOWN" else None)
                state = self.run_test(task["id"])
                self.assertIsNone(state["error"])
                requirement = self.requirement(state, "ACCESS")
                self.assertEqual(requirement["status"], "BLOCKED")
                self.assertEqual(requirement["knowledge_status"], status)
                self.assertEqual(self.current_task(task["id"]), task)

    def test_unconfirmed_task_field_cannot_support_pass(self):
        task = self.task(confirmed=False)
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        self.assertEqual(state["result"]["gates_passed"], 0)
        self.assertTrue(all(gate["status"] == "BLOCKED" for gate in state["result"]["gates"]))
        self.assertEqual(self.current_task(task["id"])["confirmed_fields"], [])

    def test_confirmed_unavailable_access_still_blocks(self):
        task = self.task(data="The business confirms that the student team cannot access the contract documents.")
        self.ai.side_effect = lambda payload: model_result(payload, {"ACCESS": "UNAVAILABLE"})
        state = self.run_test(task["id"])
        requirement = self.requirement(state, "ACCESS")
        self.assertEqual(requirement["knowledge_status"], "CONFIRMED")
        self.assertEqual(requirement["status"], "BLOCKED")
        self.assertEqual(self.current_task(task["id"])["score"], task["score"])

    def test_diagnostic_does_not_touch_task_knowledge_proposals_or_publication(self):
        task = self.task(data=None)
        self.item_status(task["id"], "data", "NEEDS_EXPERT", expert="IT department")
        published = self.client.post(f"/api/tasks/{task['id']}/publish").json()
        team = self.client.post("/api/teams", json={"name": "Alatau student team"}).json()
        proposal = self.client.post("/api/proposals", json={
            "task_id": task["id"], "team_id": team["id"],
            "solution_idea": "Review the business process with the owner.", "status": "accepted",
        }).json()
        with self.session_factory() as session:
            original_knowledge = deepcopy(session.get(InterviewSession, task["id"]).state)
        state = self.run_test(task["id"])
        self.assertEqual(self.gate(state, "ACCESS")["status"], "BLOCKED")
        self.assertEqual(self.current_task(task["id"]), published)
        self.assertEqual(self.client.get("/api/proposals").json(), [proposal])
        with self.session_factory() as session:
            self.assertEqual(session.get(InterviewSession, task["id"]).state, original_knowledge)
        self.assertEqual(self.client.post(f"/api/tasks/{task['id']}/publish").status_code, 200)
        self.assertTrue(self.current_task(task["id"])["published"])

    def test_latest_result_persists_without_another_provider_call(self):
        task = self.task()
        first = self.run_test(task["id"])
        self.assertEqual(self.latest(task["id"]), first)
        self.assertEqual(self.ai.call_count, 1)

    def test_task_edits_stale_result_and_rerun_replaces_it(self):
        task = self.task()
        first = self.run_test(task["id"])
        changed = self.client.patch(f"/api/tasks/{task['id']}", json={"success_criteria": "The owner has not yet agreed how to evaluate results."})
        self.assertEqual(changed.status_code, 200)
        stale = self.latest(task["id"])
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["result"], first["result"])
        self.assertEqual(self.ai.call_count, 1)
        updated = self.run_test(task["id"])
        self.assertFalse(updated["stale"])
        self.assertEqual(self.gate(updated, "VALIDATE")["status"], "BLOCKED")

    def test_knowledge_change_stales_saved_result(self):
        task = self.task()
        first = self.run_test(task["id"])
        self.item_status(task["id"], "data", "NEEDS_EXPERT", expert="IT department")
        stale = self.latest(task["id"])
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["result"], first["result"])
        self.assertEqual(self.ai.call_count, 1)

    def test_publication_changes_do_not_stale_information_snapshot(self):
        task = self.task()
        self.run_test(task["id"])
        self.client.post(f"/api/tasks/{task['id']}/publish")
        self.assertFalse(self.latest(task["id"])["stale"])

    def test_invalid_json_returns_recoverable_error_without_changing_task(self):
        for output in ("{not-json", {"requirements": []}, {"score": 100, "requirements": []}):
            with self.subTest(output=output):
                task = self.task()
                self.ai.side_effect = None
                self.ai.return_value = output
                state = self.run_test(task["id"])
                self.assertTrue(state["error"])
                self.assertIsNone(state["result"])
                self.assertEqual(self.current_task(task["id"]), task)

    def test_outage_preserves_previous_result_and_retry_recovers(self):
        task = self.task()
        previous = self.run_test(task["id"])
        self.ai.side_effect = RuntimeError("provider unavailable, sensitive debug details")
        failed = self.run_test(task["id"])
        self.assertTrue(failed["error"])
        self.assertNotIn("sensitive debug details", failed["error"])
        self.assertEqual(failed["result"], previous["result"])
        self.assertEqual(self.latest(task["id"])["result"], previous["result"])
        self.ai.side_effect = model_result
        retried = self.run_test(task["id"])
        self.assertIsNone(retried["error"])

    def test_invented_sources_quotes_experts_or_score_are_rejected_atomically(self):
        for change in ("reference", "quote", "expert", "score"):
            with self.subTest(change=change):
                task = self.task()
                self.ai.side_effect = model_result
                previous = self.run_test(task["id"])

                def invented(payload):
                    result = model_result(payload)
                    access = result["requirements"][2]
                    if change == "reference":
                        access["basis_refs"] = ["invented-business-source"]
                    elif change == "quote":
                        access["evidence"][0]["quote"] = "The company approved unlimited production access yesterday."
                    elif change == "expert":
                        access["expert_if_known"] = "An invented systems administrator"
                    else:
                        result["execution_score"] = 99
                    return result

                self.ai.side_effect = invented
                failed = self.run_test(task["id"])
                self.assertTrue(failed["error"])
                self.assertEqual(failed["result"], previous["result"])
                self.assertEqual(self.current_task(task["id"]), task)

    def test_not_applicable_cannot_be_inferred_from_missing_data_alone(self):
        task = self.task(data=None)
        self.ai.side_effect = lambda payload: model_result(payload, {"ACCESS": "NOT_APPLICABLE"})
        state = self.run_test(task["id"])
        self.assertTrue(state["error"] or self.gate(state, "ACCESS")["status"] == "BLOCKED")
        if state["result"] is not None:
            self.assertNotEqual(self.gate(state, "ACCESS")["status"], "NOT_APPLICABLE")

    def test_missing_resources_are_404(self):
        for method in (self.client.get, self.client.post):
            response = method("/api/tasks/999999/stress-test")
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.ai.call_count, 0)

    def test_explicit_not_applicable_knowledge_is_preserved_separately(self):
        task = self.task(data=None)
        self.item_status(task["id"], "data", "NOT_APPLICABLE")
        self.ai.side_effect = lambda payload: model_result(payload, {"ACCESS": "NOT_APPLICABLE"})
        state = self.run_test(task["id"])
        self.assertIsNone(state["error"])
        self.assertEqual(self.requirement(state, "ACCESS")["status"], "NOT_APPLICABLE")
        self.assertEqual(self.requirement(state, "ACCESS")["knowledge_status"], "NOT_APPLICABLE")

    def test_unrelated_confirmed_source_cannot_authorize_access(self):
        task = self.task(data=None)

        def unrelated_evidence(payload):
            result = model_result(payload)
            access = result["requirements"][2]
            contact = next(source for source in payload["sources"] if source["id"] == "task:contact")
            access["evidence"] = [{"source_ref": "task:contact", "quote": contact["text"]}]
            return result

        self.ai.side_effect = unrelated_evidence
        state = self.run_test(task["id"])
        self.assertTrue(state["error"] or self.gate(state, "ACCESS")["status"] == "BLOCKED")

    def test_contact_email_cannot_prove_dataset_is_not_applicable(self):
        task = self.task(data=None)

        def contact_is_not_scope(payload):
            result = model_result(payload, {"ACCESS": "NOT_APPLICABLE"})
            contact = next(source for source in payload["sources"] if source["id"] == "task:contact")
            result["requirements"][2]["evidence"] = [
                {"source_ref": "task:contact", "quote": contact["text"]},
            ]
            return result

        self.ai.side_effect = contact_is_not_scope
        state = self.run_test(task["id"])
        self.assertTrue(state["error"])
        self.assertIsNone(state["result"])

    def test_one_valid_quote_cannot_hide_unrelated_or_unconfirmed_evidence(self):
        for field in ("contact", "data"):
            with self.subTest(field=field):
                task = self.task()
                if field == "data":
                    self.item_status(task["id"], "data", "CONFIRMED", value=task["data"])
                    with self.session_factory() as session:
                        row = session.get(InterviewSession, task["id"])
                        state = deepcopy(row.state)
                        state["view"]["sources"].append({
                            "id": "old-unconfirmed", "text": "Students might receive unrestricted document access later.",
                            "role": "Business owner", "kind": "answer",
                        })
                        row.state = state
                        session.commit()

                def mixed_evidence(payload):
                    result = model_result(payload)
                    source_id = "task:contact" if field == "contact" else "old-unconfirmed"
                    source = next(source for source in payload["sources"] if source["id"] == source_id)
                    result["requirements"][2]["evidence"].append({
                        "source_ref": source_id, "quote": source["text"],
                    })
                    return result

                self.ai.side_effect = mixed_evidence
                state = self.run_test(task["id"])
                self.assertTrue(state["error"])
                self.assertIsNone(state["result"])

    def test_human_confirmation_alone_marks_previous_result_stale(self):
        task = self.task(confirmed=False)
        self.run_test(task["id"])
        confirmed = self.client.post(f"/api/tasks/{task['id']}/confirm", json={"fields": ["data"]})
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(self.latest(task["id"])["stale"])
        self.assertEqual(self.ai.call_count, 1)

    def test_each_of_five_gates_must_be_present(self):
        task = self.task()

        def omit_access(payload):
            result = model_result(payload)
            result["requirements"][2]["gate"] = "UNDERSTAND"
            return result

        self.ai.side_effect = omit_access
        state = self.run_test(task["id"])
        self.assertTrue(state["error"])
        self.assertIsNone(state["result"])

    def test_missing_information_cannot_quote_literal_null_as_business_evidence(self):
        task = self.task(data=None)
        previous = self.run_test(task["id"])
        self.assertIsNone(previous["error"])

        def quoted_null(payload):
            result = model_result(payload, {"ACCESS": "MISSING"})
            result["requirements"][2]["evidence"] = [
                {"source_ref": "task:data", "quote": "null"},
            ]
            return result

        self.ai.side_effect = quoted_null
        failed = self.run_test(task["id"])
        self.assertTrue(failed["error"])
        self.assertEqual(failed["result"], previous["result"])
        self.assertEqual(self.current_task(task["id"]), task)

    def test_task_and_knowledge_references_cannot_be_interchanged(self):
        task = self.task(need=None)
        answer = "We need to identify clauses that differ from our approved contract template."
        self.item_status(task["id"], "need", "OPEN", value=answer)

        def answer_with_reference(payload, reference):
            result = model_result(payload, {"UNDERSTAND": "MISSING"})
            sources = {source["id"]: source for source in payload["sources"]}
            self.assertIsNone(sources["task:need"]["text"])
            self.assertEqual(sources["knowledge:need"]["text"], answer)
            # Keep the requirement's business basis valid to isolate the wrong
            # quote-to-source association observed in real verification.
            for requirement in result["requirements"]:
                if any(not sources[reference]["text"] for reference in requirement["basis_refs"]):
                    requirement["basis_refs"] = ["task:context"]
            result["requirements"][0]["evidence"] = [
                {"source_ref": reference, "quote": answer},
            ]
            return result

        self.ai.side_effect = lambda payload: answer_with_reference(payload, "task:need")
        failed = self.run_test(task["id"])
        self.assertTrue(failed["error"])
        self.assertIsNone(failed["result"])
        self.assertEqual(self.current_task(task["id"]), task)

        self.ai.side_effect = lambda payload: answer_with_reference(payload, "knowledge:need")
        recovered = self.run_test(task["id"])
        self.assertIsNone(recovered["error"])
        self.assertEqual(self.gate(recovered, "UNDERSTAND")["status"], "BLOCKED")
        self.assertEqual(self.requirement(recovered, "UNDERSTAND")["knowledge_status"], "OPEN")
        self.assertEqual(self.current_task(task["id"]), task)

    def test_midflight_task_edit_never_presents_previous_snapshot_as_current(self):
        task = self.task()

        def concurrent_edit(payload):
            with self.session_factory() as session:
                row = session.get(Task, task["id"])
                row.data = "Access has been withdrawn while the analysis was running."
                row.confirmed_fields = [field for field in row.confirmed_fields if field != "data"]
                session.commit()
            return model_result(payload)

        self.ai.side_effect = concurrent_edit
        result = self.run_test(task["id"])
        self.assertTrue(result["stale"] or result["error"])
        self.assertTrue(self.latest(task["id"])["stale"])


if __name__ == "__main__":
    unittest.main()
