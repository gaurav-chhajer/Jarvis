"""Download a local speech model; never uploads recordings."""
from pathlib import Path
from faster_whisper.utils import download_model

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / ".runtime" / "whisper-small.en"
    download_model("small.en", output_dir=str(target))
    from faster_whisper import WhisperModel
    WhisperModel(str(target), device="cpu", compute_type="int8", local_files_only=True)
    (target / ".ready").touch()
    print("English accuracy model downloaded and verified.")
