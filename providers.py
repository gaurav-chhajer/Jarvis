"""Explicit answer providers; credentials never enter prompts or preferences."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
LABELS = {"codex": "Codex", "groq": "Groq", "ollama": "Ollama (offline)"}
DEFAULTS = {"codex": "Account default", "groq": "openai/gpt-oss-120b", "ollama": "llama3.1:8b"}
KEY_FILE = ROOT / ".runtime" / "groq-key.bin"


def protect_key(value, decrypt=False):
    """Windows user-bound DPAPI; never fall back to plaintext storage."""
    if sys.platform != "win32":
        raise RuntimeError("Secure key saving requires Windows. Use the key for this session instead.")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("Windows could not access the encrypted API key.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def load_key():
    if KEY_FILE.exists():
        try:
            return protect_key(KEY_FILE.read_bytes(), decrypt=True).decode("utf-8")
        except (OSError, RuntimeError, UnicodeError):
            return ""
    return os.environ.get("GROQ_API_KEY", "")


def save_key(key):
    if not key.strip():
        KEY_FILE.unlink(missing_ok=True)
        return
    encrypted = protect_key(key.strip().encode("utf-8"))
    KEY_FILE.parent.mkdir(exist_ok=True)
    temporary = KEY_FILE.with_suffix(".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(KEY_FILE)


# Overrides apply only to this child runtime, never to the user's Codex settings.
CODEX_OVERRIDES = (
    'features.shell_tool=false', 'features.code_mode=false',
    'features.code_mode_host=false', 'features.js_repl=false',
    'features.computer_use=false', 'features.browser_use=false',
    'features.image_generation=false', 'features.memory_tool=false',
    'features.codex_hooks=false',
    'features.apply_patch_freeform=false', 'features.apps=false',
    'features.view_image=false', 'features.multi_agent=false',
    'features.multi_agent_v2=false', 'agents.enabled=false',
    'web_search="disabled"', 'mcp_servers={}',
    'plugins={_default={enabled=false}}', 'apps={_default={enabled=false}}',
    'project_doc_max_bytes=0', 'model_reasoning_effort="low"',
)


def codex_client():
    from codex_windows import hide_codex_console
    hide_codex_console()
    from openai_codex import Codex, CodexConfig
    workspace = ROOT / ".runtime" / "codex-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return Codex(CodexConfig(cwd=str(workspace), config_overrides=CODEX_OVERRIDES,
                            env={"GROQ_API_KEY": "", "OPENAI_API_KEY": ""},
                            client_name="jarvis", client_title="Jarvis"))


def check_codex_account(client):
    account = client.account().account
    if account is None or getattr(account.root, "type", None) != "chatgpt":
        raise RuntimeError("Sign in with ChatGPT first: run codex login in a terminal, then Check connection.")


def check_cloud(provider, key):
    if provider == "codex":
        with codex_client() as client:
            check_codex_account(client)
        return [DEFAULTS[provider]]
    if not key.strip():
        raise RuntimeError("Enter your Groq API key in Settings, then Check connection.")
    from groq import Groq
    with Groq(api_key=key.strip(), timeout=45, max_retries=0) as client:
        return sorted(model.id for model in client.models.list().data)


def safe_error(provider, error):
    if provider == "ollama":
        return f"Ollama could not answer: {error}. Check the local service and installed model in Settings."
    if isinstance(error, RuntimeError):
        return str(error)
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return f"{LABELS[provider]} rejected authentication. Check your sign-in or API key in Settings."
    if status == 429:
        return f"{LABELS[provider]} usage limit reached. Wait and retry, or select another provider in Settings."
    return f"{LABELS[provider]} could not answer ({type(error).__name__}). Check your connection, account limits, and model in Settings. No other provider was used."


class CloudChat:
    """Ollama-shaped streaming interface for the common answer pipeline."""
    def __init__(self, provider, key=""):
        self.provider, self.key = provider, key

    def chat(self, *, model, messages, stream=False, **unused):
        chunks = self._stream(model, messages)
        if stream:
            return ({"message": {"content": text}} for text in chunks)
        return {"message": {"content": "".join(chunks)}}

    def _stream(self, model, messages):
        if self.provider == "groq":
            if not self.key.strip():
                raise RuntimeError("Enter your Groq API key in Settings before asking a question.")
            from groq import Groq
            with Groq(api_key=self.key.strip(), timeout=60, max_retries=0) as client:
                with client.chat.completions.create(model=model, messages=messages, stream=True,
                                                     max_completion_tokens=4096) as response:
                    for part in response:
                        if part.choices and part.choices[0].delta.content:
                            yield part.choices[0].delta.content
            return
        from openai_codex import Sandbox, ApprovalMode
        with codex_client() as client:
            check_codex_account(client)
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            thread = client.thread_start(
                model=None if model == DEFAULTS["codex"] else model,
                sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all,
                ephemeral=True, base_instructions=system +
                "\nYou are an answer-only chat assistant. Return text and code examples. "
                "Do not execute code, use tools, read files, or change anything on the computer.",
            )
            # JSON preserves message boundaries; prior answers are conversation data.
            prompt = json.dumps([m for m in messages if m["role"] != "system"], ensure_ascii=False)
            turn = thread.turn("Answer the latest user message in this conversation:\n" + prompt)
            for event in turn.stream():
                if event.method == "item/agentMessage/delta":
                    yield event.payload.delta
                elif event.method == "turn/completed":
                    error = getattr(event.payload.turn, "error", None)
                    status = getattr(event.payload.turn.status, "value", event.payload.turn.status)
                    if error or status != "completed":
                        raise RuntimeError("Codex did not complete the answer. Check your connection and subscription usage limits, then retry.")
