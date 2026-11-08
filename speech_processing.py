"""Recording preparation and explicit speech-recognition options."""
LANGUAGES = {"English": "en", "Automatic": None, "Hindi": "hi", "Spanish": "es",
             "French": "fr", "German": "de"}
SPEECH_MODELS = ("small.en", "base.en", "tiny.en", "tiny", "base", "small", "medium")


def prepare_audio(audio, sample_rate):
    """Keep timing/pitch correct and report problems instead of boosting noise."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError("The recording is empty or contains invalid samples. Record again.")
    if sample_rate <= 0:
        raise ValueError("Invalid microphone sample rate.")
    peak = float(np.max(np.abs(audio)))
    if peak < 0.0001:
        raise ValueError("The microphone captured silence. Check the Windows input device and microphone volume.")
    warnings = []
    if peak < 0.01:
        warnings.append("Recording is very quiet. Move closer or raise the microphone input level.")
    if float(np.mean(np.abs(audio) >= 0.99)) > 0.02:
        warnings.append("Recording is clipping. Reduce the microphone input level.")
    if sample_rate != 16000:
        import av
        frame = av.AudioFrame.from_ndarray(audio.reshape(1, -1), format="fltp", layout="mono")
        frame.sample_rate = int(sample_rate)
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
        frames = resampler.resample(frame) + resampler.resample(None)
        audio = np.concatenate([frame.to_ndarray().reshape(-1) for frame in frames])
    return np.ascontiguousarray(audio, dtype=np.float32), warnings


def transcription_options(beam_size=5, language="en"):
    return dict(task="transcribe", language=language, beam_size=beam_size,
                vad_filter=True, condition_on_previous_text=False)
