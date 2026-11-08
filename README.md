# Jarvis Assistant

Ask questions, write and debug code, or use audio as context. Speech is transcribed locally. Choose the answer provider in **Settings > Answer provider**.

## Start

Double-click `start_assistant.cmd`, or run from this folder:

```powershell
.\.venv\Scripts\python.exe meeting_minutes_app.py
```

## Answer providers

| Provider | Setup | Where answers run |
| --- | --- | --- |
| Codex (default) | Sign in with ChatGPT using `codex login`, then Check connection | OpenAI, using your Codex subscription allowance |
| Groq | Enter your API key in Settings, then Check connection | Groq, using your account limits and billing |
| Ollama (offline) | Install Ollama and download an answer model | This computer; no web search |

Codex uses the official `openai-codex` Python SDK and its pinned runtime. It reuses your Codex ChatGPT sign-in; the app does not read or copy authentication tokens. Your account must provide Codex access. API-key sign-in is deliberately rejected for this option, preventing unexpected OpenAI API billing. Keep **Account default** unless you know an available model ID. If signed out, run `codex login` in a terminal and check the connection again. [Official SDK documentation](https://learn.chatgpt.com/docs/codex-sdk), [authentication](https://learn.chatgpt.com/docs/auth).

Codex is configured for answering: ephemeral threads, read-only sandbox, denied permission escalation, and disabled shell, code execution, apps, plugins, MCP configuration, and built-in web tools. Code is displayed as examples, never automatically executed by Jarvis. The app supplies retrieved web excerpts itself.

Groq defaults to `openai/gpt-oss-120b`. Check connection validates the key and lists available models. The masked key field applies immediately for this session. **Save key securely** uses Windows DPAPI encryption tied to your Windows account and stores ciphertext in `.runtime/groq-key.bin`. To forget it, clear the field and save. Keys are never written to preferences or sent as conversation text. On other platforms, use session entry or `GROQ_API_KEY`; secure disk saving is Windows-only. A live Groq request requires your key. [Groq documentation](https://console.groq.com/docs/quickstart).

Ollama uses only `http://127.0.0.1:11434`, even if OLLAMA_HOST points elsewhere. The app can start an installed Ollama runtime, including `.runtime/ollama/ollama.exe`. Download models before disconnecting:

```powershell
ollama pull llama3.1:8b
```

Offline mode also prevents speech-model downloads. This installation includes Tiny and the more accurate English `small.en` model. On a fresh installation, run `python install_speech_model.py` while online to install English accuracy mode before using Ollama offline. Other speech models download on first use with an online provider selected. If a model is missing, choose an installed one. Ollama preloads the selected answer model and keeps it warm for up to 30 minutes. CPU performance depends on hardware, model size, and answer length.

Providers never silently fall back to one another. A failure displays an error; select another provider explicitly in Settings. Provider/model selection and the web preference persist across launches. Switching providers resets conversation history. The visible transcript remains available as context: clear it before sending a question if you do not want it included.

## Ask and use audio

- Type in **Ask anything**, then press Enter, Send, or Ctrl+Enter. Shift+Enter inserts a new line. Audio is optional.
- Ask follow-up questions; up to four recent exchanges are retained in memory. The answer pane displays the latest response, with monospace code blocks.
- Record your default microphone, then stop to transcribe; or open an audio file. The app does not capture system audio or meeting speakers automatically. Transcription happens after recording stops.
- Review or edit the transcript while idle. A blank question answers questions heard in the audio, or explains its main points. Disable **Answer automatically after transcription** to review first.
- Speech defaults to **small.en**, **English**, and accurate decoding (five candidates). It favors accuracy over Tiny's speed. **Fast transcription** is optional and less thorough. English-only `.en` models require English; choose a multilingual model for another language. These preferences persist across launches.
- Copy or Save answers as Markdown or text. **New chat** clears the conversation, answer, and optional context after confirmation.

Answers render Markdown headings, bold/italic text, inline code, links, lists, quotations, and fenced code while streaming. Code keeps indentation and scrolls horizontally for long lines. Right-click a code block and choose **Copy code** to copy only its contents. The main Copy and Save actions retain the original Markdown for use in editors.

Microphone recordings use the device's native sample rate and are explicitly resampled to 16 kHz for Whisper. The app reports very quiet audio, clipping, dropped input buffers, and low recognition confidence. Suspect transcripts pause automatic answering so you can edit and Send. Silent recordings show an error instead of being transcribed. Starting a new transcription clears the previous transcript so a failed recording cannot reuse old context. For misheard English, keep Small.en and English selected, turn Fast transcription off, speak near the microphone, and review the transcript. This app captures the default microphone, not meeting participants' system audio.

With Codex or Groq, questions, included transcript, relevant search excerpts, and recent chat are sent to the selected provider. Audio files are never uploaded. Speech recognition remains local. Codex ephemeral threads avoid normal saved conversation threads, but provider data policies and runtime diagnostics still apply; this is not a zero-retention guarantee.

Automatic web search is available with online providers for current-information questions and explicit search requests. Say "search the web" to request verification. Disable **Allow automatic web search** in Settings to prevent search queries. This does not make Codex or Groq offline; select Ollama for offline answers.

Search uses up to three result excerpts, cached in memory for 60 seconds. Clear typed questions skip query rewriting; context-dependent queries may be rewritten by the selected provider. Search queries can contain relevant question or transcript details. Click **Search sources** links for full pages. Excerpts can be incomplete; answers without search are not live internet verification. Failed searches show an error. Models can make mistakes.

## Install on another computer

Install Python 3.10+, then:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For Codex sign-in, install the official Codex CLI if `codex login` is unavailable. For Ollama, install [Ollama](https://ollama.com/download) and pull the model above. Linux may also need `sudo apt install python3-tk libportaudio2`; use `.venv/bin/python` instead of the Windows interpreter path.

This Windows environment reuses some system packages. The provider dependencies are installed in the project virtual environment; unrelated global-package dependency warnings do not indicate a failed Jarvis installation.

## Privacy and shortcuts

Minimize Jarvis to collapse it into a small floating J icon that stays above other windows.
Click the icon to restore the full window, or drag it to reposition it. Recording and answers
continue while collapsed. Close the full window to quit.

On Windows 10 version 2004+ and Windows 11, Settings can exclude the main window from compatible screen captures. The status reports Windows confirmation. Test with your meeting app; capture methods vary. Separate system dialogs are not covered. Other operating systems currently have no capture exclusion.

On Windows, **Hide taskbar button** removes only Jarvis's taskbar button; its window stays visible. Right-click the Jarvis notification-area icon and choose **Show Jarvis** to restore the taskbar button or **Quit** to exit. The notification-area icon remains visible.

Ctrl+O opens audio, Ctrl+S saves, Ctrl+, opens Settings, and Esc returns to the workspace. Settings scroll in smaller windows; the minimum window is 1000 x 640.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest test_audio_assistant test_providers -q
.\.venv\Scripts\python.exe verify_providers.py --provider codex
.\.venv\Scripts\python.exe verify_providers.py --provider ollama
```

The manual checks send a sample math/coding question to the chosen provider; Codex consumes subscription allowance. Groq is covered with mocked streaming/authentication tests until a key is entered.
