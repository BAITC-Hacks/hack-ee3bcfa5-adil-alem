"""Request-specific output constraints; no provider/network requests occur."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.services import ai_stress_test
from app.stress_schemas import StressAIResult


GATE_FIELDS = {
    "UNDERSTAND": "need", "START": "context", "ACCESS": "data",
    "VALIDATE": "success_criteria", "DELIVER": "expected_result",
}
VALUES = {
    "context": "The company reviews supplier contracts by hand.",
    "need": "Identify clauses that differ from the approved contract template.",
    "data": "The team has approved access to forty anonymized contracts.",
    "success_criteria": "The owner will check the report against twenty reviewed contracts.",
    "expected_result": "A review report with the affected clauses and document references.",
}


def snapshot(*, confirmed=False):
    fields = (*VALUES, "constraints", "users", "contact", "interaction_format")
    items = []
    sources = []
    for field in fields:
        value = VALUES.get(field) if confirmed or field in {"context", "need"} else None
        status = "CONFIRMED" if confirmed and value else "OPEN"
        items.append({
            "field": field, "value": value, "status": status,
            "confirmed": status == "CONFIRMED", "source": None,
            "source_role": "Business owner", "expert": None,
            "conflicting_source": None,
        })
        sources.append({
            "id": f"task:{field}", "field": field,
            "text": None if field == "need" and not confirmed else value,
            "kind": "task_field", "role": "Business owner",
            "knowledge_status": status, "confirmed": status == "CONFIRMED", "expert": None,
        })
    sources.extend([
        {"id": "knowledge:need", "field": "need", "text": VALUES["need"],
         "kind": "knowledge_map", "role": "Business owner", "knowledge_status": "CONFIRMED" if confirmed else "OPEN",
         "confirmed": confirmed, "expert": None},
        {"id": "answer-need", "field": None, "text": VALUES["need"],
         "kind": "answer", "role": "Business owner", "knowledge_status": None,
         "confirmed": False, "expert": None},
        {"id": "action-data", "field": None, "text": "needs_expert: IT department",
         "kind": "action", "role": "Business owner", "knowledge_status": None,
         "confirmed": False, "expert": None},
    ])
    next(item for item in items if item["field"] == "need")["source"] = "answer-need"
    return {"task": {"title": None, "industry": None}, "items": items, "sources": sources}


def valid_plan():
    return {"requirements": [
        {
            "gate": gate, "field": field,
            "requirement": f"The challenge requires information about {field.replace('_', ' ')}.",
            "required_information": f"What is known about {field.replace('_', ' ')}?",
            "basis_refs": ["knowledge:need"], "evidence": [], "assessment": "MISSING",
        }
        for gate, field in GATE_FIELDS.items()
    ]}


class StressRequestSchemaTests(unittest.TestCase):
    def test_basis_enum_excludes_empty_action_and_unknown_source_ids(self):
        schema = ai_stress_test._request_schema(snapshot())
        schema.model_validate(valid_plan())
        for reference in ("task:need", "task:data", "action-data", "invented-ref"):
            with self.subTest(reference=reference):
                plan = valid_plan()
                plan["requirements"][0]["basis_refs"] = [reference]
                with self.assertRaises(ValidationError):
                    schema.model_validate(plan)
        for reference in ("task:context", "knowledge:need", "answer-need"):
            with self.subTest(valid_reference=reference):
                plan = valid_plan()
                plan["requirements"][0]["basis_refs"] = [reference]
                schema.model_validate(plan)

    def test_no_confirmed_sources_forbids_supported_unavailable_and_evidence(self):
        schema = ai_stress_test._request_schema(snapshot())
        for assessment in ("SUPPORTED", "UNAVAILABLE", "NOT_APPLICABLE"):
            with self.subTest(assessment=assessment):
                plan = valid_plan()
                plan["requirements"][0]["assessment"] = assessment
                with self.assertRaises(ValidationError):
                    schema.model_validate(plan)
        plan = valid_plan()
        plan["requirements"][0]["evidence"] = [
            {"source_ref": "knowledge:need", "quote": VALUES["need"]},
        ]
        with self.assertRaises(ValidationError):
            schema.model_validate(plan)

    def test_explicit_not_applicable_allows_na_without_fabricated_evidence(self):
        payload = snapshot()
        next(item for item in payload["items"] if item["field"] == "data")["status"] = "NOT_APPLICABLE"
        schema = ai_stress_test._request_schema(payload)
        plan = valid_plan()
        plan["requirements"][2]["assessment"] = "NOT_APPLICABLE"
        schema.model_validate(plan)
        plan["requirements"][2]["evidence"] = [{"source_ref": "task:data", "quote": "null"}]
        with self.assertRaises(ValidationError):
            schema.model_validate(plan)

    def test_evidence_enum_uses_current_effective_confirmation_not_old_task_flags(self):
        payload = snapshot(confirmed=True)
        data = next(item for item in payload["items"] if item["field"] == "data")
        data.update(status="UNKNOWN", confirmed=False, value=None)
        # task:data deliberately retains its earlier confirmed text, just like
        # the real snapshot when new interview knowledge marks access unknown.
        payload["sources"].append({
            "id": "old-answer", "field": None, "text": VALUES["need"],
            "kind": "answer", "role": "Business owner", "knowledge_status": None,
            "confirmed": False, "expert": None,
        })
        schema = ai_stress_test._request_schema(payload)
        for reference in ("task:data", "old-answer", "action-data", "task:contact"):
            with self.subTest(reference=reference):
                plan = valid_plan()
                plan["requirements"][0]["evidence"] = [{"source_ref": reference, "quote": "Anything"}]
                with self.assertRaises(ValidationError):
                    schema.model_validate(plan)
        for reference in ("task:need", "knowledge:need", "answer-need"):
            with self.subTest(valid_reference=reference):
                plan = valid_plan()
                plan["requirements"][0]["assessment"] = "SUPPORTED"
                plan["requirements"][0]["evidence"] = [{"source_ref": reference, "quote": VALUES["need"]}]
                schema.model_validate(plan)

    def test_request_specific_result_is_compatible_with_base_contract(self):
        result = ai_stress_test._request_schema(snapshot()).model_validate(valid_plan())
        self.assertIsInstance(result, StressAIResult)
        self.assertEqual(StressAIResult.model_validate(result).model_dump(), valid_plan())
        self.assertEqual(StressAIResult.model_validate_json(result.model_dump_json()).model_dump(), valid_plan())

    def test_empty_business_input_does_not_call_provider(self):
        payload = snapshot()
        for item in payload["items"]:
            item.update(value=None, status="OPEN", confirmed=False)
        for source in payload["sources"]:
            if source["kind"] != "action":
                source["text"] = None
        with patch("app.services.ai_stress_test.ai_interviewer.generate_structured") as provider:
            with self.assertRaises(ValueError):
                ai_stress_test.generate_stress_test(payload)
            provider.assert_not_called()

    def test_adapter_passes_request_specific_schema_without_rewriting_sources(self):
        payload = snapshot()
        before = deepcopy(payload)

        def provider(body, prompt, schema, *args, **kwargs):
            self.assertEqual(body, before)
            invalid = valid_plan()
            invalid["requirements"][0]["basis_refs"] = ["task:need"]
            with self.assertRaises(ValidationError):
                schema.model_validate(invalid)
            return schema.model_validate(valid_plan())

        with patch("app.services.ai_stress_test.ai_interviewer.generate_structured", side_effect=provider) as mocked:
            result = ai_stress_test.generate_stress_test(payload)
            self.assertIsInstance(result, StressAIResult)
            mocked.assert_called_once()
        self.assertEqual(payload, before)


if __name__ == "__main__":
    unittest.main()
