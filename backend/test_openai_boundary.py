"""No network: verify the real SDK adapter contract with mocked responses."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.interview_schemas import InterviewAIResult
from app.services import ai_interviewer
from app.services import ai_stress_test
from app.stress_schemas import StressAIResult


STRESS_PAYLOAD = {
    "sources": [{"id": "task:context", "field": "context", "kind": "task_field",
                 "text": "Employees review contracts manually."}],
    "items": [{"field": "context", "value": "Employees review contracts manually.",
               "status": "OPEN", "confirmed": False, "source": None}],
}


class OpenAIBoundaryTests(unittest.TestCase):
    def test_missing_key_is_recoverable_and_never_calls_provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(ai_interviewer, "OpenAI") as sdk:
            with self.assertRaisesRegex(ai_interviewer.InterviewAIError, "not configured"):
                ai_interviewer.generate_interview({})
            sdk.assert_not_called()

    def test_structured_adapter_uses_config_and_no_storage(self):
        expected = InterviewAIResult(extractions=[], questions=[], can_finish=True)
        sdk = MagicMock()
        client = sdk.return_value.__enter__.return_value
        client.responses.parse.return_value = SimpleNamespace(output_parsed=expected)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key", "OPENAI_MODEL": "test-model"}), patch.object(ai_interviewer, "OpenAI", sdk):
            result = ai_interviewer.generate_interview({"mode": "batch", "sources": []})
        self.assertEqual(result, expected)
        kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertIs(kwargs["text_format"], InterviewAIResult)
        self.assertIs(kwargs["store"], False)
        self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
        self.assertNotIn("tools", kwargs)

    def test_refusal_or_incomplete_output_is_controlled(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key"}), patch.object(ai_interviewer, "OpenAI") as sdk:
            sdk.return_value.__enter__.return_value.responses.parse.return_value = SimpleNamespace(output_parsed=None)
            with self.assertRaisesRegex(ai_interviewer.InterviewAIError, "valid interview response"):
                ai_interviewer.generate_interview({})

    def test_provider_error_does_not_leak_body_or_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key"}), patch.object(ai_interviewer, "OpenAI") as sdk:
            sdk.return_value.__enter__.return_value.responses.parse.side_effect = RuntimeError("secret-provider-body unit-test-key")
            with self.assertRaises(ai_interviewer.InterviewAIError) as result:
                ai_interviewer.generate_interview({})
        self.assertNotIn("secret-provider-body", str(result.exception))
        self.assertNotIn("unit-test-key", str(result.exception))
        self.assertIn("saved", str(result.exception))

    def test_execution_adapter_uses_shared_model_and_dedicated_schema(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key", "OPENAI_MODEL": "gpt-5.4-mini"}), patch.object(ai_interviewer, "OpenAI") as sdk:
            expected = object()
            client = sdk.return_value.__enter__.return_value
            client.responses.parse.return_value = SimpleNamespace(output_parsed=expected)
            result = ai_stress_test.generate_stress_test(STRESS_PAYLOAD)
        self.assertIs(result, expected)
        kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.4-mini")
        self.assertTrue(issubclass(kwargs["text_format"], StressAIResult))
        self.assertIs(kwargs["store"], False)
        self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
        self.assertNotIn("tools", kwargs)

    def test_execution_missing_configuration_never_calls_provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(ai_interviewer, "OpenAI") as sdk:
            with self.assertRaisesRegex(ai_interviewer.InterviewAIError, "execution test is not configured"):
                ai_stress_test.generate_stress_test(STRESS_PAYLOAD)
            sdk.assert_not_called()

    def test_shared_default_model_is_the_verified_model(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key", "OPENAI_MODEL": ""}), patch.object(ai_interviewer, "OpenAI") as sdk:
            sdk.return_value.__enter__.return_value.responses.parse.return_value = SimpleNamespace(output_parsed=object())
            ai_stress_test.generate_stress_test(STRESS_PAYLOAD)
            ai_interviewer.generate_interview({})
            calls = sdk.return_value.__enter__.return_value.responses.parse.call_args_list
            self.assertEqual([call.kwargs["model"] for call in calls], ["gpt-5.4-mini", "gpt-5.4-mini"])


if __name__ == "__main__":
    unittest.main()
