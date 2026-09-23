"""Interview regression checks with an isolated DB and mocked OpenAI responses.

No test uses an API key or sends a request to OpenAI. The provider boundary is
mocked, so response validation and the complete HTTP/database workflow still run.
"""

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, main
from app.services import ai_interviewer
from app.services.scoring import calculate_score


DRAFT = (
    "Our Almaty training center tracks attendance by hand. "
    "Staff cannot easily identify students who stopped attending."
)
ANSWERS = {
    "context": "Our Almaty training center tracks attendance by hand.",
    "need": "We need to identify students who stop attending our courses.",
    "users": "Course coordinators and instructors will use the information.",
    "data": "Attendance registers contain daily records for the past year.",
    "constraints": "Student records must remain inside our existing office network.",
    "expected_result": "An attendance report that course coordinators can review weekly.",
    "success_criteria": "Reduce the time spent reviewing attendance by 25 percent.",
    "contact": "training-owner@example.com",
    "interaction_format": "The course owner can meet students online every Tuesday.",
}
QUESTIONS = {
    "context": "What happens in the current attendance process?",
    "need": "What problem does this create for your training center?",
    "users": "Who is affected by the attendance problem?",
    "data": "What information is currently recorded about attendance?",
    "constraints": "What restrictions apply to this work?",
    "expected_result": "What outcome would help the training center?",
    "success_criteria": "How would you know the situation had improved?",
    "contact": "Who can answer questions about the attendance process?",
    "interaction_format": "How can the course team work with students?",
}


def model_result(payload, extractions=()):
    """A deterministic provider fixture, not a production interview fallback."""
    extractions = list(extractions)
    filled = {item["field"] for item in extractions}
    fields = [field for field in payload["eligible_fields"] if field not in filled]
    fields = fields[:payload["question_count"]]
    return {
        "extractions": extractions,
        "questions": [
            {"field": field, "text": QUESTIONS[field], "difficulty": difficulty}
            for field, difficulty in zip(fields, ["QUICK", "THINK", "DEEP"])
        ],
        "can_finish": not fields,
    }


def extraction(payload, field, value, conflicting_with=None):
    source = next(source for source in reversed(payload["sources"])
                  if value in source["text"])
    return {"field": field, "value": value, "source": source["id"],
            "conflicting_with": conflicting_with}


class InterviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(temp.name) / 'interview.db'}",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        session_factory = sessionmaker(bind=self.engine)

        def test_database():
            with session_factory() as session:
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
            "app.services.interview.ai_interviewer.generate_interview",
            side_effect=model_result,
        ))

    def task(self, **fields):
        response = self.client.post("/api/tasks", json=fields)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def current_task(self, task_id):
        response = self.client.get(f"/api/tasks/{task_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def post(self, task_id, action, body=None):
        response = self.client.post(
            f"/api/tasks/{task_id}/interview/{action}", json=body,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start(self, **fields):
        task = self.task(context=DRAFT, **fields)
        return task["id"], self.post(task["id"], "start")

    def state(self, task_id):
        response = self.client.get(f"/api/tasks/{task_id}/interview")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def respond(self, task_id, question, action="answer", **data):
        return self.post(task_id, "respond", {
            "question_id": question["id"], "action": action, **data,
        })

    @staticmethod
    def item(state, field):
        return next(item for item in state["items"] if item["field"] == field)

    def test_initial_batch_is_three_relevant_questions_and_missing_stays_missing(self):
        task_id, state = self.start()
        self.assertIsNone(state["error"])
        self.assertEqual(len(state["questions"]), 3)
        self.assertEqual(len({q["field"] for q in state["questions"]}), 3)
        self.assertLessEqual(sum(q["difficulty"] == "DEEP" for q in state["questions"]), 1)
        for question in state["questions"]:
            self.assertEqual(question["text"], QUESTIONS[question["field"]])
        self.assertEqual(self.current_task(task_id)["context"], DRAFT)
        for field in ("data", "users", "need", "contact"):
            self.assertIsNone(self.current_task(task_id)[field])
            self.assertIsNone(self.item(state, field)["value"])
            self.assertFalse(self.item(state, field)["confirmed"])

    def test_extracted_values_are_exact_user_quotes_with_provenance(self):
        quote = "Staff cannot easily identify students who stopped attending."

        def extract_need(payload):
            return model_result(payload, [extraction(payload, "need", quote)])

        self.ai.side_effect = extract_need
        task_id, state = self.start()
        item = self.item(state, "need")
        self.assertEqual(item["value"], quote)
        original = next(source for source in state["sources"] if source["id"] == item["source"])
        self.assertEqual(original["text"], DRAFT)
        self.assertEqual(item["source_role"], original["role"])
        self.assertFalse(item["confirmed"])
        task = self.current_task(task_id)
        self.assertIsNone(task["need"])
        self.assertEqual(task["score"], 0)
        self.assertEqual(task["confirmed_fields"], [])
        self.assertEqual(len(state["questions"]), 3)
        self.assertNotIn("need", [question["field"] for question in state["questions"]])

    def test_complete_extraction_finishes_without_asking_already_supplied_information(self):
        original = " ".join(ANSWERS.values())

        def extract_every_gap(payload):
            return model_result(payload, [
                extraction(payload, field, ANSWERS[field])
                for field in payload["eligible_fields"]
            ])

        self.ai.side_effect = extract_every_gap
        task_id = self.task(context=original)["id"]
        state = self.post(task_id, "start")
        self.assertIsNone(state["error"])
        self.assertEqual(state["questions"], [])
        self.assertEqual(state["status"], "complete")
        for field, value in ANSWERS.items():
            if field != "context":
                self.assertEqual(self.item(state, field)["value"], value)
                self.assertIsNone(self.current_task(task_id)[field])
            self.assertFalse(self.item(state, field)["confirmed"])
        self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_batch_size_tracks_remaining_gaps_after_extraction(self):
        original = " ".join(ANSWERS.values())
        for remaining in (1, 2, 3, 5):
            with self.subTest(remaining=remaining):
                def extract_some(payload):
                    filled = payload["eligible_fields"][:-remaining]
                    return model_result(payload, [extraction(payload, field, ANSWERS[field]) for field in filled])

                self.ai.side_effect = extract_some
                task_id = self.task(context=original)["id"]
                state = self.post(task_id, "start")
                self.assertIsNone(state["error"])
                self.assertEqual(len(state["questions"]), min(3, remaining))
                for question in state["questions"]:
                    self.assertIsNone(self.item(state, question["field"])["value"])

    def test_question_about_just_extracted_information_is_rejected(self):
        def repeat_known_fact(payload):
            result = model_result(payload)
            result["extractions"] = [extraction(payload, "need", "Staff cannot easily identify students who stopped attending.")]
            return result

        self.ai.side_effect = repeat_known_fact
        task_id, state = self.start()
        self.assertTrue(state["error"])
        self.assertEqual(state["questions"], [])
        self.assertIsNone(self.item(state, "need")["value"])
        self.assertIsNone(self.current_task(task_id)["need"])

    def test_answer_covering_multiple_questions_advances_to_unanswered_gaps(self):
        task_id, state = self.start()
        supplied_fields = [question["field"] for question in state["questions"]]
        answer = " ".join(ANSWERS[field] for field in supplied_fields)
        self.ai.side_effect = lambda payload: model_result(payload, [
            extraction(payload, field, ANSWERS[field]) for field in supplied_fields
        ])
        changed = self.respond(task_id, state["questions"][0], answer=answer)
        self.assertIsNone(changed["error"])
        self.assertEqual(len(changed["questions"]), 3)
        self.assertFalse(set(supplied_fields) & {q["field"] for q in changed["questions"]})
        for field in supplied_fields:
            self.assertEqual(self.item(changed, field)["value"], ANSWERS[field])
            self.assertFalse(self.item(changed, field)["confirmed"])
            self.assertIsNone(self.current_task(task_id)[field])
        self.assertEqual(sum(source["text"] == answer for source in changed["sources"]), 1)
        self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_unsupported_fact_is_rejected_without_partial_mutation(self):
        def invented(payload):
            result = model_result(payload, [extraction(payload, "need", "Staff cannot easily identify students who stopped attending.")])
            result["extractions"].append({
                "field": "data", "value": "The database contains ten million student records.",
                "source": payload["sources"][0]["id"], "conflicting_with": None,
            })
            return result

        self.ai.side_effect = invented
        task_id, state = self.start()
        self.assertTrue(state["error"])
        self.assertEqual(state["questions"], [])
        self.assertIsNone(self.current_task(task_id)["need"])
        self.assertIsNone(self.current_task(task_id)["data"])
        self.assertEqual(self.current_task(task_id)["context"], DRAFT)

    def test_unknown_source_is_rejected(self):
        def wrong_source(payload):
            result = model_result(payload)
            result["extractions"] = [{
                "field": "need", "value": DRAFT, "source": "invented-source",
                "conflicting_with": None,
            }]
            return result

        self.ai.side_effect = wrong_source
        task_id, state = self.start()
        self.assertTrue(state["error"])
        self.assertIsNone(self.current_task(task_id)["need"])

    def test_invalid_model_data_has_recoverable_error_and_saved_draft(self):
        for bad in ("{broken JSON", {}, {"questions": [], "extractions": [], "can_finish": "not-a-bool"}):
            with self.subTest(data=bad):
                self.ai.side_effect = lambda payload, bad=bad: bad
                task_id, state = self.start()
                self.assertTrue(state["error"])
                self.assertEqual(state["questions"], [])
                self.assertEqual(self.current_task(task_id)["context"], DRAFT)
                self.assertEqual(self.state(task_id), state)

    def test_outage_preserves_draft_and_retry_recovers(self):
        self.ai.side_effect = ai_interviewer.InterviewAIError("AI unavailable; retry.")
        task_id, state = self.start()
        self.assertTrue(state["error"])
        self.assertEqual(state["questions"], [])
        self.assertEqual(self.current_task(task_id)["context"], DRAFT)
        self.ai.side_effect = model_result
        retried = self.post(task_id, "retry")
        self.assertIsNone(retried["error"])
        self.assertEqual(len(retried["questions"]), 3)
        self.assertEqual(retried["sources"], state["sources"])

    def test_dont_understand_rephrases_same_question_without_answer(self):
        task_id, state = self.start()
        question = state["questions"][0]
        before = self.current_task(task_id)

        def rephrase(payload):
            self.assertEqual(payload["mode"], "rephrase")
            result = model_result(payload)
            result["questions"][0]["text"] = "What is happening in this part of your work?"
            return result

        self.ai.side_effect = rephrase
        changed = self.respond(task_id, question, "dont_understand")
        self.assertIsNone(changed["error"])
        replacement = next(q for q in changed["questions"] if q["field"] == question["field"])
        self.assertEqual(replacement["text"], "What is happening in this part of your work?")
        self.assertIsNone(self.item(changed, question["field"])["value"])
        self.assertEqual(self.current_task(task_id), before)

    def test_explicit_unknown_is_not_asked_again(self):
        task_id, state = self.start()
        question = state["questions"][0]
        changed = self.respond(task_id, question, "dont_know")
        self.assertEqual(self.item(changed, question["field"])["status"], "UNKNOWN")
        self.assertFalse(self.item(changed, question["field"])["confirmed"])
        for pending in list(changed["questions"]):
            changed = self.respond(task_id, pending, "dont_know")
        self.assertNotIn(question["field"], [q["field"] for q in changed["questions"]])
        for call in self.ai.call_args_list[1:]:
            self.assertNotIn(question["field"], call.args[0]["eligible_fields"])

    def test_unchanged_rephrase_is_rejected_and_retry_preserves_sources(self):
        task_id, state = self.start()
        question = state["questions"][0]

        def unchanged(payload):
            result = model_result(payload)
            result["questions"][0]["text"] = "  " + question["text"].upper() + "  "
            return result

        self.ai.side_effect = unchanged
        changed = self.respond(task_id, question, "dont_understand")
        self.assertTrue(changed["error"])
        self.assertEqual(changed["questions"], state["questions"])
        self.assertIsNone(self.item(changed, question["field"])["value"])

        def simplified(payload):
            result = model_result(payload)
            result["questions"][0]["text"] = "What do you want to change in this work?"
            return result

        self.ai.side_effect = simplified
        retried = self.post(task_id, "retry")
        self.assertIsNone(retried["error"])
        self.assertEqual(retried["sources"], changed["sources"])
        self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_needs_expert_keeps_original_role_and_does_not_invent_one(self):
        for expert in ("Айгүл — учебный координатор", None):
            with self.subTest(expert=expert):
                task_id, state = self.start()
                question = state["questions"][0]
                changed = self.respond(task_id, question, "needs_expert", expert=expert)
                item = self.item(changed, question["field"])
                self.assertEqual(item["status"], "NEEDS_EXPERT")
                self.assertEqual(item["expert"], expert)
                self.assertFalse(item["confirmed"])
                self.assertIsNone(item["value"])
                self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_not_applicable_is_separate_and_verification_does_not_loop(self):
        task_id, state = self.start()
        question = state["questions"][0]
        changed = self.respond(task_id, question, "not_applicable")
        self.assertEqual(self.item(changed, question["field"])["status"], "OPEN")
        checks = [q for q in changed["questions"] if q["field"] == question["field"]]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["kind"], "not_applicable_check")
        checked = self.respond(task_id, checks[0], "not_applicable")
        self.assertEqual(self.item(checked, question["field"])["status"], "NOT_APPLICABLE")
        self.assertNotIn(question["field"], [q["field"] for q in checked["questions"]])
        self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_vague_answer_does_not_imply_an_explicit_unknown_action(self):
        task_id, state = self.start()
        question = state["questions"][0]
        changed = self.respond(task_id, question, answer="I'm not really sure about that yet.")
        self.assertNotEqual(self.item(changed, question["field"])["status"], "UNKNOWN")
        self.assertTrue(any(source["text"] == "I'm not really sure about that yet."
                            for source in changed["sources"]))

    def test_failed_answer_is_saved_once_and_retry_extracts_it(self):
        task_id, state = self.start()
        question = state["questions"][0]
        answer = ANSWERS[question["field"]]
        self.ai.side_effect = ai_interviewer.InterviewAIError("AI unavailable; retry.")
        failed = self.respond(task_id, question, answer=answer, source_role="Course coordinator")
        self.assertTrue(failed["error"])
        self.assertEqual(sum(s["text"] == answer for s in failed["sources"]), 1)
        self.assertEqual(self.state(task_id), failed)

        def extract_answer(payload):
            return model_result(payload, [extraction(payload, question["field"], answer)])

        self.ai.side_effect = extract_answer
        retried = self.post(task_id, "retry")
        self.assertIsNone(retried["error"])
        self.assertEqual(sum(s["text"] == answer for s in retried["sources"]), 1)
        item = self.item(retried, question["field"])
        self.assertEqual(item["value"], answer)
        self.assertEqual(item["source_role"], "Course coordinator")
        self.assertFalse(item["confirmed"])
        self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_ai_score_or_confirmation_injection_changes_nothing(self):
        for injection in ({"score": 100}, {"readiness_level": "priority"}, {"confirmed_fields": ["context"]}):
            with self.subTest(injection=injection):
                self.ai.side_effect = lambda payload, injection=injection: {**model_result(payload), **injection}
                task_id, state = self.start()
                self.assertTrue(state["error"])
                task = self.current_task(task_id)
                self.assertEqual(task["score"], 0)
                self.assertEqual(task["readiness_level"], "draft")
                self.assertEqual(task["confirmed_fields"], [])

    def test_readiness_details_never_enter_provider_payload(self):
        task_id = self.task(context=ANSWERS["context"], need=ANSWERS["need"])["id"]
        response = self.client.post(f"/api/tasks/{task_id}/confirm", json={"fields": ["context", "need"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 20)
        self.post(task_id, "start")
        self.assertGreater(self.ai.call_count, 0)

        def assert_no_scores(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"score", "readiness_level", "breakdown", "potential_gain"})
                for child in value.values():
                    assert_no_scores(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_scores(child)

        for call in self.ai.call_args_list:
            assert_no_scores(call.args[0])

    def test_confirmation_uses_existing_engine_and_edit_clears_it(self):
        task_id, state = self.start()
        question = state["questions"][0]
        field = question["field"]
        answer = ANSWERS[field]
        self.ai.side_effect = lambda payload: model_result(payload, [extraction(payload, field, answer)])
        changed = self.respond(task_id, question, answer=answer)
        self.assertFalse(self.item(changed, field)["confirmed"])
        task = self.current_task(task_id)
        self.assertEqual(task["score"], 0)
        self.assertIsNone(task[field])
        reviewed = self.client.patch(f"/api/tasks/{task_id}", json={field: answer})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["score"], 0)
        task = reviewed.json()
        confirmation = self.client.post(f"/api/tasks/{task_id}/confirm", json={"fields": [field]})
        self.assertEqual(confirmation.status_code, 200, confirmation.text)
        expected = calculate_score(task, [field])["score"]
        self.assertGreater(expected, 0)
        self.assertEqual(confirmation.json()["score"], expected)
        confirmed = self.item(self.state(task_id), field)
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertTrue(confirmed["confirmed"])

        edited = self.client.patch(f"/api/tasks/{task_id}", json={field: answer + " The owner clarified this."})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["score"], 0)
        self.assertNotIn(field, edited.json()["confirmed_fields"])
        self.assertFalse(self.item(self.state(task_id), field)["confirmed"])

    def test_finish_for_now_at_zero_preserves_information_and_allows_publication(self):
        task_id, state = self.start(title="Attendance review", need="Course coordinators need to review attendance more easily.")
        finished = self.post(task_id, "finish")
        self.assertIn(finished["status"], ("paused", "complete"))
        self.assertEqual(finished["sources"], state["sources"])
        self.assertEqual(self.current_task(task_id)["score"], 0)
        self.assertEqual(self.state(task_id), finished)
        published = self.client.post(f"/api/tasks/{task_id}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        self.assertTrue(published.json()["published"])
        self.assertEqual(self.client.get(f"/api/catalog/{task_id}").status_code, 200)

    def test_classified_gaps_allow_completion_below_one_hundred(self):
        task_id, state = self.start(need=ANSWERS["need"])
        for _ in range(12):
            if not state["questions"]:
                break
            state = self.respond(task_id, state["questions"][0], "dont_know")
            self.assertLessEqual(len(state["questions"]), 3)
        self.assertEqual(state["questions"], [])
        self.assertEqual(state["status"], "complete")
        self.assertLess(self.current_task(task_id)["score"], 100)

    def test_missing_resources_and_invalid_responses_return_404_or_422(self):
        self.assertEqual(self.client.get("/api/tasks/999/interview").status_code, 404)
        self.assertEqual(self.client.post("/api/tasks/999/interview/start").status_code, 404)
        task_id, state = self.start()
        question = state["questions"][0]
        for body in (
            {"question_id": question["id"], "action": "answer", "answer": "   "},
            {"question_id": question["id"], "action": "invented_action"},
            {"question_id": question["id"], "action": "dont_know", "score": 100},
        ):
            with self.subTest(body=body):
                response = self.client.post(f"/api/tasks/{task_id}/interview/respond", json=body)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.state(task_id), state)

    def test_invalid_batch_size_difficulty_or_leading_question_is_rejected(self):
        def too_many(result):
            result["questions"].append({"field": "constraints", "text": QUESTIONS["constraints"], "difficulty": "QUICK"})

        def too_few(result):
            result["questions"].pop()

        def too_difficult(result):
            result["questions"][0]["difficulty"] = "DEEP"

        def duplicate_field(result):
            result["questions"][1] = result["questions"][0].copy()

        def leading(result):
            result["questions"][0]["text"] = "What data do you have, for example spreadsheets or PDFs?"

        for modify in (too_many, too_few, too_difficult, duplicate_field, leading):
            with self.subTest(validation=modify.__name__):
                def malformed(payload):
                    result = model_result(payload)
                    modify(result)
                    return result

                self.ai.side_effect = malformed
                task_id, state = self.start()
                self.assertTrue(state["error"])
                self.assertEqual(state["questions"], [])
                self.assertEqual(self.current_task(task_id)["score"], 0)

    def test_rephrase_cannot_fill_an_answer(self):
        task_id, state = self.start()
        question = state["questions"][0]

        def fills_answer(payload):
            return model_result(payload, [extraction(payload, question["field"], DRAFT)])

        self.ai.side_effect = fills_answer
        changed = self.respond(task_id, question, "dont_understand")
        self.assertTrue(changed["error"])
        self.assertEqual(changed["questions"], state["questions"])
        self.assertIsNone(self.item(changed, question["field"])["value"])

    def test_start_is_idempotent_and_stale_answer_is_rejected(self):
        task_id, state = self.start()
        calls = self.ai.call_count
        self.assertEqual(self.post(task_id, "start"), state)
        self.assertEqual(self.ai.call_count, calls)
        question = state["questions"][0]
        changed = self.respond(task_id, question, "dont_know")
        repeated = self.client.post(f"/api/tasks/{task_id}/interview/respond", json={
            "question_id": question["id"], "action": "dont_know",
        })
        self.assertEqual(repeated.status_code, 409, repeated.text)
        self.assertEqual(self.state(task_id), changed)

    def test_extraction_cannot_overwrite_an_explicit_unknown(self):
        task_id, state = self.start()
        unknown = state["questions"][0]
        changed = self.respond(task_id, unknown, "dont_know")
        next_question = changed["questions"][0]
        answer = ANSWERS[next_question["field"]]
        self.ai.side_effect = lambda payload: model_result(payload, [extraction(payload, unknown["field"], answer)])
        changed = self.respond(task_id, next_question, answer=answer)
        self.assertIsNone(changed["error"])
        self.assertEqual(self.item(changed, unknown["field"])["status"], "UNKNOWN")
        self.assertIsNone(self.item(changed, unknown["field"])["value"])

    def test_conflict_keeps_both_original_claims_without_overwriting_confirmed_task(self):
        task = self.task(context=DRAFT, need=ANSWERS["need"])
        task_id = task["id"]
        confirmed = self.client.post(f"/api/tasks/{task_id}/confirm", json={"fields": ["need"]})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        state = self.post(task_id, "start")
        earlier = self.item(state, "need")["source"]
        contradiction = "We do not need attendance reports; the actual problem is invoice delays."

        def conflict(payload):
            return model_result(payload, [extraction(payload, "need", contradiction, conflicting_with=earlier)])

        self.ai.side_effect = conflict
        changed = self.respond(task_id, state["questions"][0], answer=contradiction)
        self.assertIsNone(changed["error"])
        self.assertEqual(self.item(changed, "need")["status"], "CONFLICT")
        self.assertFalse(self.item(changed, "need")["confirmed"])
        self.assertEqual(self.item(changed, "need")["conflicting_source"], earlier)
        self.assertEqual(self.item(self.state(task_id), "need")["status"], "CONFLICT")
        source_texts = [source["text"] for source in changed["sources"]]
        self.assertIn(ANSWERS["need"], source_texts)
        self.assertIn(contradiction, source_texts)
        saved = self.current_task(task_id)
        self.assertEqual(saved["need"], ANSWERS["need"])
        self.assertEqual(saved["score"], confirmed.json()["score"])
        self.assertEqual(saved["confirmed_fields"], ["need"])

    def test_finish_during_outage_can_resume_and_retry_without_losing_answer(self):
        task_id, state = self.start()
        question = state["questions"][0]
        answer = ANSWERS[question["field"]]
        self.ai.side_effect = ai_interviewer.InterviewAIError("AI unavailable; retry.")
        failed = self.respond(task_id, question, answer=answer)
        finished = self.post(task_id, "finish")
        self.assertEqual(finished["status"], "paused")
        self.assertEqual(finished["sources"], failed["sources"])
        self.assertEqual(self.client.post(f"/api/tasks/{task_id}/interview/retry").status_code, 409)
        resumed = self.post(task_id, "start")
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["sources"], failed["sources"])
        self.ai.side_effect = model_result
        retried = self.post(task_id, "retry")
        self.assertIsNone(retried["error"])
        self.assertEqual(retried["sources"], failed["sources"])
        self.assertEqual(self.item(retried, question["field"])["value"], answer)

    def test_not_applicable_verification_answer_can_retract_the_action(self):
        task_id, state = self.start()
        question = state["questions"][0]
        checking = self.respond(task_id, question, "not_applicable")
        verification = next(q for q in checking["questions"] if q["field"] == question["field"])
        correction = "Actually, this does apply. I misunderstood the original question."
        changed = self.respond(task_id, verification, answer=correction)
        item = self.item(changed, question["field"])
        self.assertEqual(item["status"], "OPEN")
        self.assertEqual(item["value"], correction)
        self.assertFalse(item["confirmed"])
        self.assertTrue(any(source["text"] == correction for source in changed["sources"]))
        self.assertNotIn(question["field"], [q["field"] for q in changed["questions"]])

    def test_rephrasing_not_applicable_check_preserves_single_verification(self):
        task_id, state = self.start()
        question = state["questions"][0]
        checking = self.respond(task_id, question, "not_applicable")
        verification = next(q for q in checking["questions"] if q["field"] == question["field"])

        def rephrase(payload):
            result = model_result(payload)
            if payload["mode"] == "rephrase":
                result["questions"][0]["text"] = "What problem does this cause?"
            return result

        self.ai.side_effect = rephrase
        rephrased = self.respond(task_id, verification, "dont_understand")
        self.assertIsNone(rephrased["error"])
        simplified = next(q for q in rephrased["questions"] if q["field"] == question["field"])
        self.assertNotEqual(simplified["text"], verification["text"])
        self.assertEqual(simplified["kind"], "not_applicable_check")
        changed = self.respond(task_id, simplified, "not_applicable")
        self.assertEqual(self.item(changed, question["field"])["status"], "NOT_APPLICABLE")
        self.assertNotIn(question["field"], [q["field"] for q in changed["questions"]])

    def test_human_edit_cancels_failed_rephrase_for_that_field(self):
        task_id, state = self.start()
        question = state["questions"][0]
        self.ai.side_effect = ai_interviewer.InterviewAIError("AI unavailable; retry.")
        failed = self.respond(task_id, question, "dont_understand")
        self.assertTrue(failed["error"])
        answer = ANSWERS[question["field"]]
        edited = self.client.patch(f"/api/tasks/{task_id}", json={question["field"]: answer})
        self.assertEqual(edited.status_code, 200, edited.text)
        state = self.state(task_id)
        self.assertIsNone(state["error"])
        self.assertEqual(self.item(state, question["field"])["value"], answer)
        self.assertNotIn(question["field"], [q["field"] for q in state["questions"]])
        self.ai.reset_mock()
        self.assertEqual(self.post(task_id, "retry"), state)
        self.ai.assert_not_called()


if __name__ == "__main__":
    unittest.main()
