"""Provider boundaries are testable without a model key or network call."""
import os
import sys
import unittest
from importlib.util import find_spec
from types import SimpleNamespace
from unittest.mock import Mock, patch

from coach.models import MODEL, api_key, make_model


class GeminiModelTests(unittest.TestCase):
    def test_only_gemini_keys_are_accepted_with_whitespace_trimmed(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "old-key"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_API_KEY or GEMINI_API_KEY"):
                api_key()
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "  google-test-key ", "GEMINI_API_KEY": "gemini-test-key"}, clear=True):
            self.assertEqual(api_key(), "google-test-key")
        with patch.dict(os.environ, {"GOOGLE_API_KEY": " ", "GEMINI_API_KEY": " gemini-test-key "}, clear=True):
            self.assertEqual(api_key(), "gemini-test-key")

    def test_developer_api_and_no_fallback_or_retry_are_explicit(self):
        constructor = Mock()
        module = SimpleNamespace(ChatGoogleGenerativeAI=constructor)
        with patch.dict(sys.modules, {"langchain_google_genai": module}), patch.dict(os.environ, {
            "GEMINI_API_KEY": "gemini-test-key", "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "should-not-be-used", "ANTHROPIC_API_KEY": "old-key",
        }, clear=True):
            make_model(max_tokens=2048)
        self.assertEqual(constructor.call_count, 1)
        options = constructor.call_args.kwargs
        self.assertEqual(options["model"], MODEL)
        self.assertEqual(MODEL, "gemini-3.5-flash-lite")
        self.assertFalse(options["vertexai"])
        self.assertEqual(options["api_key"], "gemini-test-key")
        self.assertEqual(options["max_retries"], 0)
        self.assertEqual(options["thinking_level"], "minimal")
        self.assertNotIn("thinking_budget", options)
        self.assertEqual(options["max_output_tokens"], 2048)
        self.assertNotIn("project", options)
        self.assertNotIn("tools", options)

    def test_live_mode_never_uses_offline_credentials_or_another_provider(self):
        constructor = Mock()
        with patch.dict(sys.modules, {"langchain_google_genai": SimpleNamespace(ChatGoogleGenerativeAI=constructor)}), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "old-key"}, clear=True):
            with self.assertRaises(RuntimeError):
                make_model()
        constructor.assert_not_called()

    def test_explicit_tools_only_construction_ignores_real_credentials(self):
        constructor = Mock()
        with patch.dict(sys.modules, {"langchain_google_genai": SimpleNamespace(ChatGoogleGenerativeAI=constructor)}), \
             patch.dict(os.environ, {"GOOGLE_API_KEY": "never-use-this-key"}, clear=True):
            make_model(offline=True)
        self.assertEqual(constructor.call_args.kwargs["api_key"], "offline-harness-only-not-a-real-key")
        constructor.return_value.invoke.assert_not_called()

    @unittest.skipUnless(find_spec("langchain_google_genai"), "coach SDK is optional in core CI")
    def test_real_adapter_serializes_minimal_thinking_and_tools_without_network(self):
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import StructuredTool

        with patch("socket.socket.connect", side_effect=AssertionError("No provider connection")):
            model = make_model(offline=True)
            tool = StructuredTool.from_function(
                func=lambda take_id: "fixture", name="get_take_report",
                description="Read timing for one take.")
            bound = model.bind_tools([tool])
            payload = model._prepare_request(
                [HumanMessage(content="Read take fixture-one")], tools=bound.kwargs["tools"])
        self.assertEqual(payload["model"], MODEL)
        thinking = payload["config"].thinking_config
        self.assertEqual(thinking.thinking_level.value, "MINIMAL")
        self.assertIsNone(thinking.thinking_budget)
        declarations = [item.name for tool in payload["config"].tools
                        for item in (tool.function_declarations or [])]
        self.assertEqual(declarations, ["get_take_report"])


if __name__ == "__main__":
    unittest.main()
