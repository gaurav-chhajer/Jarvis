import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from meeting_minutes_app import AudioAssistantApp
from providers import CloudChat, CODEX_OVERRIDES, safe_error


class ProviderTests(unittest.TestCase):
    def test_offline_provider_never_searches_even_if_requested(self):
        app = SimpleNamespace(q=queue.Queue())
        client = Mock(chat=Mock(return_value=iter([{"message": {"content": "Answer"}}])))
        with patch("ollama.Client", return_value=client) as local, \
             patch("meeting_minutes_app.search_web") as web:
            AudioAssistantApp._run_llm(app, "local", "news", use_web=True, provider="ollama")
        web.assert_not_called()
        local.assert_called_once_with(host="http://127.0.0.1:11434")

    def test_offline_speech_never_downloads_models(self):
        app = SimpleNamespace(q=queue.Queue(), _whisper=None, _whisper_size=None, _selected_provider="ollama")
        factory = Mock(side_effect=ValueError("not cached"))
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            AudioAssistantApp._transcribe(app, "audio.wav", "medium")
        self.assertTrue(factory.call_args.kwargs["local_files_only"])

    def test_groq_key_missing_does_not_request_network(self):
        with patch.dict("sys.modules", {"groq": Mock()}) as modules:
            with self.assertRaisesRegex(RuntimeError, "Enter your Groq"):
                list(CloudChat("groq")._stream("model", []))
            modules["groq"].Groq.assert_not_called()

    def test_groq_stream_and_no_credential_in_messages(self):
        part = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))])
        response = Mock()
        response.__enter__ = Mock(return_value=iter([part]))
        response.__exit__ = Mock(return_value=False)
        client = Mock()
        client.chat.completions.create.return_value = response
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=client)
        factory.return_value.__exit__ = Mock(return_value=False)
        messages = [{"role": "user", "content": "Hi"}]
        with patch.dict("sys.modules", {"groq": SimpleNamespace(Groq=factory)}):
            result = list(CloudChat("groq", "test-secret")._stream("model", messages))
        self.assertEqual(result, ["Hello"])
        self.assertEqual(client.chat.completions.create.call_args.kwargs["messages"], messages)

    def test_cloud_errors_do_not_echo_credentials_or_response_body(self):
        error = ValueError("test-secret raw response")
        self.assertNotIn("test-secret", safe_error("groq", error))
        error = SimpleNamespace(status_code=429)
        self.assertIn("usage limit", safe_error("groq", error))

    def test_selected_provider_failure_never_falls_back(self):
        app = SimpleNamespace(q=queue.Queue())
        backend = Mock(chat=Mock(side_effect=ValueError("private response")))
        with patch("meeting_minutes_app.CloudChat", return_value=backend) as cloud, \
             patch("ollama.Client") as local:
            AudioAssistantApp._run_llm(app, "model", "question", provider="groq", api_key="secret")
        cloud.assert_called_once_with("groq", "secret")
        local.assert_not_called()
        self.assertEqual(app.q.get_nowait()[0], "error")

    def test_codex_is_ephemeral_readonly_and_denies_approvals(self):
        from openai_codex import Sandbox, ApprovalMode
        client = Mock()
        client.account.return_value.account.root.type = "chatgpt"
        turn = client.thread_start.return_value.turn.return_value
        turn.stream.return_value = iter([
            SimpleNamespace(method="item/agentMessage/delta", payload=SimpleNamespace(delta="Answer")),
            SimpleNamespace(method="turn/completed", payload=SimpleNamespace(
                turn=SimpleNamespace(error=None, status="completed"))),
        ])
        context = Mock()
        context.__enter__ = Mock(return_value=client)
        context.__exit__ = Mock(return_value=False)
        with patch("providers.codex_client", return_value=context):
            self.assertEqual(list(CloudChat("codex")._stream("Account default", [])), ["Answer"])
        options = client.thread_start.call_args.kwargs
        self.assertEqual(options["sandbox"], Sandbox.read_only)
        self.assertEqual(options["approval_mode"], ApprovalMode.deny_all)
        self.assertTrue(options["ephemeral"])
        self.assertIsNone(options["model"])
        self.assertIn("features.shell_tool=false", CODEX_OVERRIDES)
        self.assertIn("features.code_mode_host=false", CODEX_OVERRIDES)


if __name__ == "__main__":
    unittest.main()
