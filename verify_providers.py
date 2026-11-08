"""Small manual live check. No credentials or account details are printed."""
import argparse
import queue
from types import SimpleNamespace
from meeting_minutes_app import AudioAssistantApp
from providers import check_cloud, protect_key

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["codex", "ollama"], default="codex")
    args = parser.parse_args()
    assert protect_key(protect_key(b"test-secret"), decrypt=True) == b"test-secret"
    if args.provider == "codex":
        check_cloud("codex", "")
    app = SimpleNamespace(q=queue.Queue())
    model = "Account default" if args.provider == "codex" else "llama3.1:8b"
    AudioAssistantApp._run_llm(app, model,
        "USER REQUEST: What is 17 times 24? Then write a Python function add(a, b) returning their sum.",
        provider=args.provider)
    events = list(app.q.queue)
    errors = [payload for kind, payload in events if kind == "error"]
    if errors:
        raise RuntimeError(errors[0])
    answer = next(payload["answer"] for kind, payload in events if kind == "answer_done")
    assert "408" in answer and "def add" in answer, answer
    print(args.provider + " live math and coding check passed; Windows encrypted-key round trip passed.")
