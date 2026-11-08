# Parakeet desktop design

Direction: Achromatic ledger, seed 1330605105. No redraws. Existing Segoe UI typography retained for the Windows app.

Question: What does my audio say, and what is the answer to my question?

General-assistant extension: questions can be asked with no audio. A multiline composer handles questions and pasted code, with Enter to send and Shift+Enter for a newline. Context is used automatically when relevant; lightweight routing chooses direct answers or web search. There are no separate web/context switches in the composer. Automatic search defaults on with an explicit online-query disclosure, and a persistent Settings privacy preference can disable it. Source links come from actual retrieved results. New chat clears conversation, answer, and source context. Code blocks use monospace formatting. Native compact layout checks and real math, follow-up, coding-syntax, web-search, and audio integration checks cover the extension.

Objects and jobs: microphone recordings, imported audio files, editable transcript, user question, streamed answer, local answer model, speech model, capture exclusion, file export, connection health.

The product's audio waveform becomes the wordmark and a real RMS-driven microphone-level monitor. No simulated waveform or invented statistics. Neutral chrome, one near-black primary action that moves from Record to Get answer after a transcript exists. Semantic color appears only for recording, connection health, errors, and the real audio level.

The open-plane rail holds two actual destinations and audio-source controls, rather than fake navigation. Main workspace pairs source with answer. Secondary configuration moves to Settings. Counts derive from transcript words; source names and recording durations are real. Empty states contain guidance, never placeholder transcript data.

Native Tkinter adaptation: no HTML, browser DOM, web fonts, mobile routing, or CSS inspector. Use Segoe UI loaded from the system, native widget checks, screenshots at 1280×800 and the supported minimum 1000×640, and real audio-to-answer integration verification. Desktop preview connectors failed to initialize; local renders come from a disposable test instance with capture exclusion off. Production defaults remain capture-excluded. Review screenshots use the previously verified synthetic recording and real model answer; new user sessions start empty.

Grid: 220px rail, 24px right gutter, flexible workspace; at 1280px, workspace is 1036px. Source/answer panes split 43/57 with a draggable 12px gutter. No shadows, gradients, vanity metrics, remote image assets, or new dependencies.

Visual review corrected high-DPI capture/render scaling, compact rail clipping, error-message overlap, and an idle progress bar that looked active. Settings now scroll in small windows. Normal and compact views keep both pane edges aligned, show all primary actions, and retain engine/capture status. Native check deliberately replaces browser DOM inspection; no unsupported browser audit is claimed.

Functional validation: five worker/service regression tests passed. The complete redesigned application's queue and automatic-answer flow transcribed the synthetic question “What is the capital of France?” and returned “The capital of France is Paris.” Controls lock during processing, answers stay read-only/selectable, and source editing restores when processing ends. No sample content is inserted into normal user sessions. Recording-state preview uses a zero-level test state without microphone capture.
