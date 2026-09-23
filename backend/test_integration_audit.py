"""Adversarial API checks. All provider calls are mocked."""
import unittest
import test_interview as fixture
from unittest.mock import patch
from app.services import ai_interviewer
import test_stress_test as stress_fixture

class IntegrationAuditTests(unittest.TestCase):
    setUp = fixture.InterviewTests.setUp
    task = fixture.InterviewTests.task
    post = fixture.InterviewTests.post
    state = fixture.InterviewTests.state
    current_task = fixture.InterviewTests.current_task

    def test_manual_edit_during_ai_does_not_get_overwritten(self):
        task = self.task(context="Employees review supplier contracts manually.")
        replacement = "Ручное уточнение: доступны только обезличенные договоры."
        def concurrent_edit(payload):
            response = self.client.patch(f"/api/tasks/{task['id']}", json={"data": replacement})
            self.assertEqual(response.status_code, 200)
            return fixture.model_result(payload)
        self.ai.side_effect = concurrent_edit
        self.post(task["id"], "start")
        view = self.state(task["id"])
        item = next(x for x in view["items"] if x["field"] == "data")
        self.assertEqual(item["value"], replacement)
        self.assertTrue(any(s["text"] == replacement for s in view["sources"]))
        self.ai.side_effect = fixture.model_result
        self.assertIsNone(self.post(task["id"], "retry")["error"])

    def test_finish_during_ai_is_not_reverted(self):
        task = self.task(context="Employees review contracts manually.")
        def finish(payload):
            self.post(task["id"], "finish")
            return fixture.model_result(payload)
        self.ai.side_effect = finish
        self.post(task["id"], "start")
        self.assertEqual(self.state(task["id"])["status"], "paused")

    def test_edit_survives_provider_failure_during_generation(self):
        task = self.task(context="Employees review contracts manually.")
        def fail(payload):
            self.client.patch(f"/api/tasks/{task['id']}", json={"users": "Закупщики компании Алматы"})
            raise TimeoutError("private provider payload must not escape")
        self.ai.side_effect = fail
        view = self.post(task["id"], "start")
        self.assertNotIn("private provider", str(view))
        self.assertTrue(any(s["text"] == "Закупщики компании Алматы" for s in view["sources"]))

    def test_unknown_and_expert_manual_answers_confirm_edit_invalidate_stress(self):
        task = self.task(**stress_fixture.FIELDS)
        task_id = task["id"]
        # Ask real missing fields, then deliberately classify their uncertainty.
        self.client.patch(f"/api/tasks/{task_id}", json={"data": None, "users": None})
        view = self.post(task_id, "start")
        for field, action in (("users", "dont_know"), ("data", "needs_expert")):
            question = next(q for q in view["questions"] if q["field"] == field)
            view = self.post(task_id, "respond", {"question_id": question["id"], "action": action, **({"expert": "IT department"} if action == "needs_expert" else {})})
        original_sources = view["sources"]
        for field in ("users", "data"):
            value = stress_fixture.FIELDS[field]
            self.assertEqual(self.client.patch(f"/api/tasks/{task_id}", json={field: value}).status_code, 200)
            self.assertEqual(self.client.post(f"/api/tasks/{task_id}/confirm", json={"fields": [field]}).status_code, 200)
            item = next(i for i in self.state(task_id)["items"] if i["field"] == field)
            self.assertEqual(item["status"], "CONFIRMED")
            self.assertIsNone(item["expert"])
        with patch("app.services.ai_stress_test.generate_stress_test", side_effect=stress_fixture.model_result):
            result = self.client.post(f"/api/tasks/{task_id}/stress-test").json()
        self.assertIsNone(result["error"])
        for field in ("data", "success_criteria"):
            self.client.patch(f"/api/tasks/{task_id}", json={field: "Новые сведения для проверки результата 25 процентов."})
            self.assertTrue(self.client.get(f"/api/tasks/{task_id}/stress-test").json()["stale"])
            self.assertNotIn(field, self.current_task(task_id)["confirmed_fields"])
        sources = self.state(task_id)["sources"]
        self.assertTrue(all(source in sources for source in original_sources))
        self.assertEqual(self.current_task(task_id)["score"], 10)

    def test_multilingual_and_edge_input_round_trip(self):
        for text in ("Қызметкерлер шарттарды ұзақ тексереді 🚀", "Сотрудники долго проверяют договоры.", "Employees review contracts.", "<script>alert(1)</script> **markdown**", "Ұ" * 20000):
            with self.subTest(text=text[:25]):
                task = self.task(context=text)
                def localized(payload):
                    self.assertEqual(payload["sources"][0]["text"], text)
                    result = fixture.model_result(payload)
                    for q in result["questions"]:
                        q["text"] = "Какую информацию нужно уточнить для этого поля?"
                    return result
                self.ai.side_effect = localized
                view = self.post(task["id"], "start")
                self.assertIsNone(view["error"])
                self.assertEqual(view["sources"][0]["text"], text)
                self.assertEqual(self.current_task(task["id"])["score"], 0)

    def test_outage_invalid_json_and_timeout_preserve_answer_retry(self):
        for error in (TimeoutError("private raw payload"), ai_interviewer.InterviewAIError("AI temporarily unavailable"), "{invalid JSON"):
            with self.subTest(error=type(error).__name__):
                self.ai.side_effect = fixture.model_result
                task = self.task(context="Employees review contracts manually.")
                view = self.post(task["id"], "start")
                question = view["questions"][0]
                self.ai.side_effect = (lambda payload: error) if isinstance(error, str) else error
                answer = "Нужно находить отличия от утверждённого шаблона договора."
                failed = self.post(task["id"], "respond", {"question_id": question["id"], "action": "answer", "answer": answer})
                self.assertIsNotNone(failed["error"])
                self.assertNotIn("private raw payload", str(failed))
                self.assertTrue(any(s["text"] == answer for s in self.state(task["id"])["sources"]))
                self.assertEqual(self.current_task(task["id"])["score"], 0)
                self.ai.side_effect = fixture.model_result
                self.assertIsNone(self.post(task["id"], "retry")["error"])

    def test_empty_whitespace_punctuation_and_repeat_confirm(self):
        for value in ("", "   ", "!!!???"):
            task = self.task(title="Validation", need=value)
            self.assertEqual(self.client.post(f"/api/tasks/{task['id']}/confirm", json={"fields": ["need"]}).status_code, 422)
            self.assertEqual(self.current_task(task["id"])["score"], 0)
        task = self.task(need="Нужно находить отличия от утверждённого шаблона договора.")
        for _ in range(2):
            response = self.client.post(f"/api/tasks/{task['id']}/confirm", json={"fields": ["need", "need"]})
            self.assertEqual(response.json()["score"], 10)
            self.assertEqual(response.json()["confirmed_fields"], ["need"])
