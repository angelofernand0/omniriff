"""Provider boundaries are testable without a model key or network call."""
import os
import sys
import unittest
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
        self.assertEqual(MODEL, "gemini-2.5-flash-lite")
        self.assertFalse(options["vertexai"])
        self.assertEqual(options["api_key"], "gemini-test-key")
        self.assertEqual(options["max_retries"], 0)
        self.assertEqual(options["thinking_budget"], 0)
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


if __name__ == "__main__":
    unittest.main()
