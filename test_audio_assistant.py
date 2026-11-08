import queue
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch

from meeting_minutes_app import AudioAssistantApp
from web_support import SearchSource, WebSearchError, recent_history, search_web
from processing import context_size_for_request, direct_search_query, MODEL_KEEP_ALIVE, needs_web_search


class AudioFlowTests(unittest.TestCase):
    def worker(self):
        return SimpleNamespace(q=queue.Queue(), _whisper=None, _whisper_size=None)

    def test_audio_file_transcription_and_silence(self):
        app = self.worker()
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text=" What is gravity? ")]), None)
        factory = Mock(return_value=model)
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            AudioAssistantApp._transcribe(app, "example.wav", "tiny")
            self.assertEqual(app.q.get_nowait()[0], "speech_feedback")
            self.assertEqual(app.q.get_nowait(), ("transcript", "What is gravity?"))
            self.assertEqual(app.q.get_nowait(), ("transcribe_done", True))
            model.transcribe.assert_called_with("example.wav", vad_filter=True, beam_size=5,
                                                task="transcribe", language="en", condition_on_previous_text=False)
            model.transcribe.return_value = (iter([]), None)
            AudioAssistantApp._transcribe(app, "silence.wav", "tiny")
            self.assertEqual(app.q.get_nowait()[0], "speech_feedback")
            self.assertEqual(app.q.get_nowait(), ("transcribe_done", False))
            self.assertEqual(factory.call_count, 1)

    def test_bad_audio_reports_error(self):
        app = self.worker()
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Mock(side_effect=ValueError("bad audio")))}):
            AudioAssistantApp._transcribe(app, "bad.wav", "tiny")
        kind, message = app.q.get_nowait()
        self.assertEqual(kind, "error")
        self.assertIn("bad audio", message)

    def test_answer_stream_uses_transcript_and_request(self):
        app = self.worker()
        chat = Mock(return_value=iter([{"message": {"content": "Gravity "}}, {"message": {"content": "attracts mass."}}]))
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(chat=chat)))}):
            AudioAssistantApp._run_llm(app, "local-model", "TRANSCRIPT: What is gravity?\nUSER REQUEST: Explain simply.")
        messages = chat.call_args.kwargs["messages"]
        self.assertIn("What is gravity?", messages[1]["content"])
        self.assertIn("Explain simply", messages[1]["content"])
        self.assertEqual(app.q.get_nowait(), ("answer_chunk", "Gravity "))
        self.assertEqual(app.q.get_nowait(), ("answer_chunk", "attracts mass."))
        kind, turn = app.q.get_nowait()
        self.assertEqual(kind, "answer_done")
        self.assertEqual(turn["answer"], "Gravity attracts mass.")
        self.assertIn("No live web search was performed", messages[1]["content"])

    def test_question_without_audio_is_accepted(self):
        var = lambda value: SimpleNamespace(get=lambda: value)
        app = SimpleNamespace(
            busy=False, recording=False, transcript=Mock(get=Mock(return_value="")),
            use_transcript=var(False), question_var=var("Explain recursion"), model_var=var("local-model"),
            allow_web=var(False), title_var=var(""), stage=Mock(), _history=[], _history_context=None,
            answer_mode=Mock(),
            show_workspace=Mock(), _dismiss_error=Mock(), generate=Mock(), _write_answer=Mock(),
            _set_busy=Mock(), set_status=Mock(), _run_llm=Mock(),
        )
        with patch("meeting_minutes_app.threading.Thread") as worker:
            AudioAssistantApp.generate(app)
        args = worker.call_args.kwargs["args"]
        self.assertIn("Explain recursion", args[1])
        self.assertNotIn("TRANSCRIPT", args[1])
        self.assertFalse(args[3])

    def test_web_answer_uses_real_sources_and_recent_history(self):
        app = self.worker()
        sources = [SearchSource("Python docs", "https://docs.python.org/3/", "Python documentation.")]
        chat = Mock(side_effect=[{"message": {"content": "Python official documentation"}},
                                 iter([{"message": {"content": "See the official docs [1]."}}])])
        history = [{"role": "user", "content": "I am learning Python."}]
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(chat=chat)))}), \
                patch("meeting_minutes_app.search_web", return_value=sources) as search:
            with patch("meeting_minutes_app.CloudChat", return_value=SimpleNamespace(chat=chat)):
                AudioAssistantApp._run_llm(app, "local-model", "Where can I find documentation?", history, True, provider="groq")
        search.assert_called_once_with("Python official documentation")
        messages = chat.call_args_list[1].kwargs["messages"]
        self.assertEqual(messages[1], history[0])
        self.assertIn(sources[0].url, messages[-1]["content"])
        events = list(app.q.queue)
        self.assertIn(("search_sources", sources), events)
        self.assertIn(sources[0].url, events[-1][1]["answer"])

    def test_web_failure_never_claims_a_searched_answer(self):
        app = self.worker()
        chat = Mock(return_value={"message": {"content": "current weather Delhi"}})
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(chat=chat)))}), \
                patch("meeting_minutes_app.search_web", side_effect=WebSearchError("Search unavailable")):
            with patch("meeting_minutes_app.CloudChat", return_value=SimpleNamespace(chat=chat)):
                AudioAssistantApp._run_llm(app, "local-model", "Weather?", use_web=True, provider="groq")
        events = list(app.q.queue)
        self.assertEqual(events[-1], ("error", "Search unavailable"))
        self.assertFalse(any(kind == "answer_chunk" for kind, _ in events))
        self.assertEqual(chat.call_count, 1)

    def test_direct_search_skips_query_generation(self):
        app = self.worker()
        chat = Mock(return_value=iter([{"message": {"content": "An answer [1]."}}]))
        sources = [SearchSource("Docs", "https://docs.python.org/", "Official documentation")]
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(chat=chat)))}), \
                patch("meeting_minutes_app.search_web", return_value=sources) as search:
            with patch("meeting_minutes_app.CloudChat", return_value=SimpleNamespace(chat=chat)):
                AudioAssistantApp._run_llm(app, "local-model", "Find Python docs", use_web=True,
                                          direct_query="Python official documentation", provider="groq")
        self.assertEqual(chat.call_count, 1)
        self.assertTrue(chat.call_args.kwargs["stream"])
        self.assertEqual(chat.call_args.kwargs["keep_alive"], MODEL_KEEP_ALIVE)
        search.assert_called_once_with("Python official documentation")

    def test_context_sizes_preserve_longer_requests(self):
        self.assertEqual(context_size_for_request("What is gravity?"), 4096)
        self.assertEqual(context_size_for_request("x" * 12000, use_web=True), 8192)
        self.assertGreater(context_size_for_request("x" * 40000), 8192)

    def test_followup_and_audio_queries_do_not_take_unsafe_shortcuts(self):
        history = [{"role": "user", "content": "Tell me about Ada Lovelace"}]
        self.assertIsNone(direct_search_query("When was she born?", history))
        self.assertIsNone(direct_search_query("What year?", history))
        self.assertEqual(direct_search_query("Find the official Python tutorial on docs.python.org.", history),
                         "Find the official Python tutorial on docs.python.org.")
        self.assertIsNone(direct_search_query("A long code request\nwith multiple lines"))

    def test_automatic_web_routing(self):
        for question in ["Write Python code for binary search", "Solve 24 * 17", "Explain recursion"]:
            self.assertFalse(needs_web_search(question), question)
        for question in ["What is the weather in Delhi today?", "What is the latest React API?",
                         "Find the official Python tutorial", "Search the web for Python docs"]:
            self.assertTrue(needs_web_search(question), question)
        self.assertFalse(needs_web_search("Summarize our meeting today", "Private meeting notes"))
        self.assertFalse(needs_web_search("", "Today we discussed our deadline and budget."))
        self.assertTrue(needs_web_search("", "What is the current stock price of Apple?"))

    def test_repeated_search_uses_short_lived_cache(self):
        rows = [{"href": "https://example.com/cache", "body": "Cached test excerpt"}]
        client = Mock(text=Mock(return_value=rows))
        fake = SimpleNamespace(DDGS=Mock(return_value=client))
        with patch.dict(sys.modules, {"ddgs": fake}), patch("web_support._SEARCH_CACHE", {}), \
                patch("web_support.time.monotonic", return_value=100) as clock:
            first = search_web("cache test")
            second = search_web("cache test")
            self.assertEqual(first, second)
            self.assertIsNot(first, second)
            self.assertEqual(client.text.call_count, 1)
            clock.return_value = 161
            search_web("cache test")
            self.assertEqual(client.text.call_count, 2)

    def test_accurate_speech_mode_keeps_original_decoder(self):
        app = self.worker()
        model = Mock(transcribe=Mock(return_value=(iter([]), None)))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Mock(return_value=model))}):
            AudioAssistantApp._transcribe(app, "example.wav", "tiny", beam_size=5)
        model.transcribe.assert_called_once_with("example.wav", vad_filter=True, beam_size=5,
                                                task="transcribe", language="en", condition_on_previous_text=False)

    def test_model_preloads_without_duplicate_requests(self):
        app = SimpleNamespace(q=queue.Queue(), busy=False, recording=False,
                              _warming_model=None, _preloaded_model=None)
        generate = Mock()
        def thread(target, daemon):
            return SimpleNamespace(start=target)
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(generate=generate)))}), \
                patch("meeting_minutes_app.threading.Thread", side_effect=thread):
            AudioAssistantApp._preload_model(app, "local-model")
            AudioAssistantApp._preload_model(app, "local-model")
        generate.assert_called_once_with(model="local-model", prompt="", keep_alive=MODEL_KEEP_ALIVE,
                                         options={"num_ctx": 4096})
        self.assertEqual(app.q.get_nowait(), ("model_warm", "local-model"))

    def test_search_discards_invalid_and_duplicate_links(self):
        rows = [{"href": "javascript:alert(1)", "body": "Bad link"},
                {"href": "https://example.com/a", "title": "Example", "body": "A usable excerpt"},
                {"href": "https://example.com/a", "body": "Duplicate"},
                {"href": "https://user:password@example.com/", "body": "Credential URL"}]
        fake = SimpleNamespace(DDGS=Mock(return_value=Mock(text=Mock(return_value=rows))))
        with patch.dict(sys.modules, {"ddgs": fake}):
            sources = search_web("a question")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].url, "https://example.com/a")

    def test_history_is_bounded_and_keeps_no_system_messages(self):
        messages = [{"role": "system", "content": "discard"}] + [
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 3000 + str(i)} for i in range(20)]
        history = recent_history(messages)
        self.assertEqual(len(history), 8)
        self.assertTrue(all(len(row["content"]) < 1700 for row in history))
        self.assertTrue(history[-1]["content"].endswith("19"))

    def test_generation_failure_reports_error(self):
        app = self.worker()
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(chat=Mock(side_effect=ConnectionError("offline")))))}):
            AudioAssistantApp._run_llm(app, "local-model", "question")
        self.assertEqual(app.q.get_nowait()[0], "error")

    def test_refresh_starts_installed_ollama_when_offline(self):
        app = self.worker()
        listing = Mock(side_effect=[ConnectionError("offline"), {"models": [{"model": "llama3.1:8b"}]}])
        def thread(target, daemon):
            return SimpleNamespace(start=target)
        with patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=Mock(return_value=SimpleNamespace(list=listing)))}), \
                patch("meeting_minutes_app.threading.Thread", side_effect=thread), \
                patch("meeting_minutes_app.shutil.which", return_value=None), \
                patch("meeting_minutes_app.Path.is_file", return_value=True), \
                patch("meeting_minutes_app.Path.open", mock_open()), \
                patch("meeting_minutes_app.time.sleep"), \
                patch("meeting_minutes_app.subprocess.Popen") as launch:
            AudioAssistantApp.refresh_models(app)
        self.assertEqual(launch.call_args.args[0][1], "serve")
        self.assertEqual(app.q.get_nowait()[0], "status")
        self.assertEqual(app.q.get_nowait(), ("models", ["llama3.1:8b"]))


if __name__ == "__main__":
    unittest.main()
