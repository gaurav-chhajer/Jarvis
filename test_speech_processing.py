import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np

from speech_processing import prepare_audio, transcription_options
from meeting_minutes_app import AudioAssistantApp


class SpeechTests(unittest.TestCase):
    def test_resampling_preserves_pitch_and_duration(self):
        for rate in (44100, 48000, 16000):
            with self.subTest(rate=rate):
                signal = 0.2 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
                audio, warnings = prepare_audio(signal, rate)
                self.assertLessEqual(abs(len(audio) - 16000), 1)
                frequency = np.argmax(np.abs(np.fft.rfft(audio))) * 16000 / len(audio)
                self.assertAlmostEqual(frequency, 440, delta=1)
                self.assertEqual(audio.dtype, np.float32)
                self.assertFalse(warnings)

    def test_silence_invalid_and_multichannel_are_not_transcribed(self):
        for signal in (np.zeros(16000), np.array([np.nan]), np.array([]), np.ones((100, 2))):
            with self.subTest(shape=signal.shape), self.assertRaises(ValueError):
                prepare_audio(signal, 16000)

    def test_quiet_and_clipped_audio_are_flagged_without_boosting_noise(self):
        quiet = np.full(16000, .001, dtype=np.float32)
        audio, warnings = prepare_audio(quiet, 16000)
        self.assertTrue(warnings)
        np.testing.assert_array_equal(audio, quiet)
        self.assertTrue(prepare_audio(np.ones(16000), 16000)[1])

    def test_english_accuracy_options_and_optional_fast_mode(self):
        options = transcription_options()
        self.assertEqual(options["language"], "en")
        self.assertEqual(options["beam_size"], 5)
        self.assertFalse(options["condition_on_previous_text"])
        self.assertEqual(transcription_options(1, None)["beam_size"], 1)
        self.assertIsNone(transcription_options(1, None)["language"])

    def test_uncertain_transcript_is_marked_for_review(self):
        app = SimpleNamespace(q=queue.Queue(), _whisper=None, _whisper_size=None)
        segment = SimpleNamespace(text="Possibly misheard", avg_logprob=-1.4)
        model = Mock(transcribe=Mock(return_value=(iter([segment]), None)))
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=Mock(return_value=model))}):
            AudioAssistantApp._transcribe(app, "test.wav", "small.en")
        events = list(app.q.queue)
        feedback = next(payload for kind, payload in events if kind == "speech_feedback")
        self.assertTrue(feedback[1])
        self.assertIn("confidence", feedback[0])
        self.assertIn(("transcript", "Possibly misheard"), events)

    def test_recording_uses_device_rate_and_reports_dropped_buffers(self):
        stream = Mock()
        factory = Mock(return_value=stream)
        app = SimpleNamespace(
            _start_recording=Mock(), _install_hint=Mock(), _show_error=Mock(), frames=[],
            import_btn=Mock(), show_workspace=Mock(), _dismiss_error=Mock(), stage=Mock(),
            _source=Mock(), _sync_controls=Mock(), rec_btn=Mock(), gen_btn=Mock(), set_status=Mock(),
        )
        device = SimpleNamespace(query_devices=Mock(return_value={"default_samplerate": 48000}), InputStream=factory)
        with patch.dict("sys.modules", {"sounddevice": device}):
            AudioAssistantApp._start_recording(app)
        self.assertEqual(factory.call_args.kwargs["samplerate"], 48000)
        self.assertEqual(factory.call_args.kwargs["latency"], "high")
        callback = factory.call_args.kwargs["callback"]
        callback(np.full((100, 1), .1), 100, None, "input overflow")
        self.assertEqual(len(app.frames), 1)
        self.assertIn("input overflow", app._recording_warnings)


if __name__ == "__main__":
    unittest.main()
