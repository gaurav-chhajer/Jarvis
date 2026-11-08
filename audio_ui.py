"""Native desktop workspace. Presentation is separate from local audio/LLM workers."""
import sys
import re
import json
from pathlib import Path
import webbrowser
import tkinter as tk
from providers import LABELS, DEFAULTS, load_key, save_key
from answer_formatting import format_answer
from speech_processing import LANGUAGES, SPEECH_MODELS
from tkinter import font as tkfont, messagebox, ttk


class PromptBox(tk.Text):
    """A multiline composer synchronized with the request StringVar."""
    def __init__(self, parent, variable, **options):
        super().__init__(parent, **options)
        self.variable = variable
        self._updating = False
        self._trace = variable.trace_add("write", self._pull)
        self.bind("<<Modified>>", self._push)
        self.bind("<Destroy>", self._destroyed)
        self.edit_modified(False)

    def _push(self, event=None):
        if not self.edit_modified():
            return
        self.edit_modified(False)
        if not self._updating:
            self._updating = True
            try:
                self.variable.set(self.get("1.0", "end-1c"))
            finally:
                self._updating = False

    def _pull(self, *_):
        if self._updating:
            return
        value = self.variable.get()
        if value == self.get("1.0", "end-1c"):
            return
        self._updating = True
        state = self.cget("state")
        try:
            self.configure(state="normal")
            self.delete("1.0", "end")
            self.insert("1.0", value)
            self.edit_modified(False)
        finally:
            self.configure(state=state)
            self._updating = False

    def _destroyed(self, event):
        if event.widget is self:
            self.variable.trace_remove("write", self._trace)


class AudioWorkspaceUI:
    BG = "#f8f8f8"
    WHITE = "#ffffff"
    INK = "#171717"
    MUTED = "#626262"
    LINE = "#e6e6e6"
    BLUE = "#1d5fbf"
    GREEN = "#286438"
    RED = "#b4232c"

    def _build_ui(self):
        self.configure(background=self.BG)
        families = set(tkfont.families(self))
        self.face = "Segoe UI" if "Segoe UI" in families else "TkDefaultFont"
        self.option_add("*Font", (self.face, 10))
        self.option_add("*TCombobox*Listbox.font", (self.face, 10))
        self._style_widgets()
        self._view = "workspace"
        self._operation = None
        self._audio_level = 0.0
        self._retry_action = None
        self._last_audio = None
        self._placeholders = {}
        self._source = tk.StringVar(value="No audio added")
        self.engine_status = tk.StringVar(value="Connecting to Ollama…")
        self.engine_detail = tk.StringVar(value="Checking your local answer model.")
        self.privacy_summary = tk.StringVar(value="Checking capture exclusion…")
        self.stage = tk.StringVar(value="Ready to record")
        self.status = tk.StringVar(value="Ask any question, or add audio for context.")
        self.question_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.provider_var = tk.StringVar(value="Codex")
        self.groq_key_var = tk.StringVar(value=load_key())
        self._provider_models = dict(DEFAULTS)
        self._selected_provider = "codex"
        self.whisper_var = tk.StringVar(value="small.en")
        self.speech_language = tk.StringVar(value="English")
        self.speech_feedback = tk.StringVar(value="English accuracy mode. Review the transcript before relying on it.")
        self.auto_answer = tk.BooleanVar(value=True)
        self.fast_transcription = tk.BooleanVar(value=False)
        self._preferences_file = Path(__file__).with_name("assistant_preferences.json")
        allowed = True
        if self._preferences_file.exists():
            try:
                stored = json.loads(self._preferences_file.read_text(encoding="utf-8"))
                allowed = stored.get("allow_web") is True
                provider = stored.get("provider", "codex")
                if provider in LABELS:
                    self._selected_provider = provider
                    self.provider_var.set(LABELS[provider])
                for name, value in stored.get("models", {}).items():
                    if name in DEFAULTS and isinstance(value, str) and value.strip():
                        self._provider_models[name] = value
                if stored.get("speech_model") in SPEECH_MODELS:
                    self.whisper_var.set(stored["speech_model"])
                if stored.get("speech_language") in LANGUAGES:
                    self.speech_language.set(stored["speech_language"])
                self.fast_transcription.set(stored.get("fast_transcription") is True)
            except (OSError, ValueError, AttributeError):
                allowed = False
        self.allow_web = tk.BooleanVar(value=allowed)
        self.model_var.set(self._provider_models[self._selected_provider])
        self.engine_status.set(f"Checking {LABELS[self._selected_provider]}...")
        self.engine_detail.set("Checking your selected answer provider.")
        self.answer_mode = tk.StringVar(value="Automatic · web queries may go online." if allowed else "Web access disabled in Settings.")
        self.capture_excluded = tk.BooleanVar(value=sys.platform == "win32")
        self.capture_status = tk.StringVar(value="Waiting for window…")
        self.transcript_count = tk.StringVar(value="0 words")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # At 1280px: 220px audio rail + 1036px work area + 24px right gutter.
        rail = tk.Frame(self, bg=self.BG, width=220)
        rail.grid(row=0, column=0, rowspan=2, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(8, weight=1)
        brand = tk.Frame(rail, bg=self.BG)
        brand.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        mark = tk.Canvas(brand, width=27, height=30, bg=self.BG, highlightthickness=0)
        mark.pack(side="left", padx=(0, 10))
        for x, y in [(4, 10), (12, 3), (20, 7)]:
            mark.create_line(x, y, x, 30-y, fill=self.INK, width=4, capstyle="round")
        tk.Label(brand, text="Jarvis", bg=self.BG, fg=self.INK,
                 font=(self.face, 17, "bold")).pack(anchor="w")
        tk.Label(brand, text="Personal assistant", bg=self.BG, fg=self.MUTED,
                 font=(self.face, 10)).pack(anchor="w")
        nav = tk.Frame(rail, bg=self.BG)
        nav.grid(row=1, column=0, sticky="ew", padx=16)
        self.workspace_nav = self._nav_button(nav, "Workspace", self.show_workspace)
        self.settings_nav = self._nav_button(nav, "Settings", self.show_settings)
        ttk.Separator(rail).grid(row=2, column=0, sticky="ew", padx=24, pady=12)
        tk.Label(rail, text="Optional audio", bg=self.BG, fg=self.MUTED, anchor="w").grid(
            row=3, column=0, sticky="ew", padx=24, pady=(0, 8))
        actions = tk.Frame(rail, bg=self.BG)
        actions.grid(row=4, column=0, sticky="ew", padx=20)
        self.rec_btn = ttk.Button(actions, text="Record audio", command=self.toggle_record)
        self.rec_btn.pack(fill="x")
        self.import_btn = ttk.Button(actions, text="Open audio file…", command=self.open_audio)
        self.import_btn.pack(fill="x", pady=(8, 0))
        monitor = tk.Frame(rail, bg=self.BG)
        monitor.grid(row=5, column=0, sticky="ew", padx=24, pady=(14, 0))
        self.rec_label = tk.Label(monitor, text="00:00", bg=self.BG, fg=self.INK,
                                  font=("Consolas", 20))
        self.rec_label.pack(anchor="w")
        tk.Label(monitor, textvariable=self.stage, bg=self.BG, fg=self.MUTED,
                 font=(self.face, 9), wraplength=172, justify="left").pack(anchor="w", pady=(3, 8))
        self.level_canvas = tk.Canvas(monitor, width=168, height=24, bg=self.BG, highlightthickness=0)
        self.level_canvas.pack(anchor="w")
        self._paint_input_level()
        tk.Label(rail, textvariable=self._source, bg=self.BG, fg=self.MUTED, justify="left",
                 wraplength=172, font=(self.face, 9)).grid(row=6, column=0, sticky="w", padx=24, pady=8)
        bottom = tk.Frame(rail, bg=self.BG)
        bottom.grid(row=9, column=0, sticky="ew", padx=24, pady=8)
        self.engine_dot = tk.Label(bottom, text="●", bg=self.BG, fg=self.MUTED, font=(self.face, 9))
        self.engine_dot.grid(row=0, column=0, sticky="w", padx=(0, 6))
        tk.Label(bottom, textvariable=self.engine_status, bg=self.BG, fg=self.INK,
                 wraplength=150, justify="left", font=(self.face, 10)).grid(row=0, column=1, sticky="w")
        tk.Label(bottom, text="Speech stays local", bg=self.BG, fg=self.MUTED,
                 font=(self.face, 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 8))
        tk.Label(bottom, textvariable=self.privacy_summary, bg=self.BG, fg=self.MUTED,
                 font=(self.face, 9), wraplength=172, justify="left").grid(row=2, column=0, columnspan=2, sticky="w")

        self.content = tk.Frame(self, bg=self.BG)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 24), pady=(24, 12))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.workspace = tk.Frame(self.content, bg=self.BG)
        self.workspace.grid(row=0, column=0, sticky="nsew")
        self.workspace.grid_columnconfigure(0, weight=1)
        self.workspace.grid_rowconfigure(2, weight=1)
        heading = tk.Frame(self.workspace, bg=self.BG)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        heading.grid_columnconfigure(0, weight=1)
        tk.Label(heading, text="Assistant workspace", bg=self.BG, fg=self.INK,
                 font=(self.face, 24)).grid(row=0, column=0, sticky="w")
        tk.Label(heading, text="Ask a question, bring audio, or search the web.", bg=self.BG,
                 fg=self.MUTED, font=(self.face, 11)).grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.new_chat_btn = ttk.Button(heading, text="New chat", command=self.new_chat, width=0)
        self.new_chat_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        self.error_frame = tk.Frame(self.workspace, bg="#fff5f5", highlightbackground="#ecc4c7", highlightthickness=1)
        self.error_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.error_frame.grid_columnconfigure(0, weight=1)
        self.error_message = tk.StringVar()
        self.error_label = tk.Label(self.error_frame, textvariable=self.error_message, bg="#fff5f5",
                                    fg="#81222b", wraplength=600, justify="left", anchor="w", padx=12, pady=10)
        self.error_label.grid(row=0, column=0, sticky="ew")
        self.retry_btn = ttk.Button(self.error_frame, text="Retry", style="Quiet.TButton", command=self.retry_last_action)
        self.retry_btn.grid(row=0, column=1, padx=4)
        ttk.Button(self.error_frame, text="Dismiss", style="Quiet.TButton", command=self._dismiss_error).grid(row=0, column=2, padx=(0, 8))
        self.error_frame.grid_remove()
        self.panes = ttk.PanedWindow(self.workspace, orient="horizontal")
        self.panes.grid(row=2, column=0, sticky="nsew")
        left = self._panel(self.panes)
        right = self._panel(self.panes)
        self.panes.add(left, weight=4)
        self.panes.add(right, weight=6)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)
        for panel in (left, right):
            panel.grid_columnconfigure(0, weight=1)
        left_head = self._panel_header(left, "Context")
        self.clear_btn = ttk.Button(left_head, text="Clear", style="Quiet.TButton", command=self.clear_transcript)
        self.clear_btn.pack(side="right")
        tk.Label(left_head, textvariable=self.transcript_count, bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).pack(side="right", padx=8)
        self.transcript = self._text_with_scroll(left)
        self._add_empty_state(self.transcript, "Add optional context", "Record or open audio, or paste text and code. You can also ask a question directly.")
        self.transcript.bind("<<Modified>>", self._transcript_modified)
        self.transcript.bind("<FocusIn>", lambda event: self._refresh_empty_states())
        self.transcript.bind("<FocusOut>", lambda event: self._refresh_empty_states())
        tk.Label(left, text="Editable while the assistant is idle", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9), anchor="w", padx=18, pady=12).grid(row=2, column=0, sticky="ew")
        right_head = self._panel_header(right, "Answer")
        self.save_btn = ttk.Button(right_head, text="Save…", style="Quiet.TButton", command=self.save_answer)
        self.save_btn.pack(side="right")
        self.copy_btn = ttk.Button(right_head, text="Copy", style="Quiet.TButton", command=self.copy_answer)
        self.copy_btn.pack(side="right", padx=4)
        self.answer = self._text_with_scroll(right)
        horizontal = ttk.Scrollbar(self.answer.master, orient="horizontal", command=self.answer.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.answer.configure(xscrollcommand=horizontal.set)
        self.answer.bind("<Button-3>", self._answer_menu)
        self.answer.configure(state="disabled")
        self._add_empty_state(self.answer, "What can I help with?", "Ask about writing, code, explanations, or a problem. Context and web search are handled automatically.")
        composer = tk.Frame(right, bg=self.WHITE, padx=18, pady=16)
        composer.grid(row=2, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        tk.Label(composer, text="Ask anything", bg=self.WHITE, fg=self.INK,
                 font=(self.face, 10)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.question_entry = PromptBox(composer, self.question_var, font=(self.face, 11), height=3, width=1,
                                        wrap="word", padx=10, pady=8, undo=True, relief="flat", bd=0,
                                        highlightthickness=1, highlightbackground="#cfcfcf", highlightcolor=self.INK,
                                        bg=self.WHITE, fg=self.INK, insertbackground=self.INK)
        self.question_entry.grid(row=1, column=0, sticky="ew")
        self.question_entry.bind("<Return>", self._submit_question)
        self.question_entry.bind("<Shift-Return>", self._question_newline)
        tk.Label(composer, text="Shift+Enter: new line", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).grid(row=0, column=1, sticky="e", pady=(0, 8))
        self.gen_btn = ttk.Button(composer, text="Send", style="Primary.TButton", command=self.generate, width=7)
        self.gen_btn.grid(row=1, column=1, padx=(10, 0), sticky="ns")
        suggestions = tk.Frame(composer, bg=self.WHITE)
        suggestions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 6))
        self.suggestion_buttons = []
        for label, request in [("Summarize", "Summarize the transcript if provided, or our conversation."),
                               ("Explain simply", "Explain the topic in simple terms."),
                               ("Key takeaways", "What are the key takeaways from the transcript or our conversation?")]:
            button = ttk.Button(suggestions, text=label, style="Suggestion.TButton",
                                command=lambda value=request: self._choose_question(value))
            button.pack(side="left", padx=(0, 6))
            self.suggestion_buttons.append(button)
        tk.Label(composer, textvariable=self.answer_mode, bg=self.WHITE,
                 fg=self.MUTED, font=(self.face, 9)).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._build_settings()
        footer = tk.Frame(self, bg=self.BG)
        footer.grid(row=1, column=1, sticky="ew", padx=(0, 24), pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=self.status, bg=self.BG, fg=self.MUTED,
                 anchor="w", font=(self.face, 9)).grid(row=0, column=0, sticky="ew")
        progress_well = tk.Frame(footer, width=72, height=3, bg=self.LINE)
        progress_well.grid(row=0, column=1, padx=(12, 0))
        progress_well.pack_propagate(False)
        self.progress = ttk.Progressbar(progress_well, mode="determinate", value=0,
                                       style="Activity.Horizontal.TProgressbar")
        self.progress.pack(fill="both", expand=True)
        self.bind("<Control-Return>", lambda event: self.generate())
        self.bind("<Control-o>", lambda event: self.open_audio())
        self.bind("<Control-s>", lambda event: self.save_answer())
        self.bind("<Control-comma>", lambda event: self.show_settings())
        self.bind("<Escape>", lambda event: self.show_workspace())
        self.capture_status.trace_add("write", lambda *_: self._privacy_changed())
        self.question_var.trace_add("write", lambda *_: self._sync_controls())
        self.allow_web.trace_add("write", lambda *_: self.answer_mode.set(
            "Automatic · web queries may go online." if self.allow_web.get()
            else "Web access disabled in Settings."))
        if sys.platform != "win32":
            self._privacy_changed()
        self.error_label.bind("<Configure>", lambda event: self.error_label.configure(wraplength=max(200, event.width-24)))
        self.show_workspace()
        self._sync_controls()
        self.after_idle(self._initial_split)

    def _style_widgets(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=(self.face, 10), background=self.BG, foreground=self.INK)
        style.configure("TButton", padding=(12, 7), background=self.WHITE, bordercolor="#d4d4d4",
                        lightcolor=self.WHITE, darkcolor=self.WHITE, focuscolor=self.INK, relief="flat")
        style.map("TButton", background=[("disabled", "#f0f0f0"), ("active", "#eeeeee")],
                  foreground=[("disabled", "#6b6b6b")], bordercolor=[("focus", "#555555")])
        style.configure("Primary.TButton", background=self.INK, foreground=self.WHITE,
                        bordercolor=self.INK, lightcolor=self.INK, darkcolor=self.INK)
        style.map("Primary.TButton", background=[("disabled", "#e9e9e9"), ("active", "#333333")],
                  foreground=[("disabled", "#626262"), ("!disabled", self.WHITE)])
        style.configure("Recording.TButton", background=self.RED, foreground=self.WHITE, bordercolor=self.RED)
        style.map("Recording.TButton", background=[("active", "#8f1c24")], foreground=[("!disabled", self.WHITE)])
        style.configure("Quiet.TButton", borderwidth=0, background=self.WHITE, padding=(8, 5), width=0)
        style.map("Quiet.TButton", background=[("disabled", self.WHITE), ("active", "#eeeeee")])
        style.configure("Suggestion.TButton", padding=(7, 5), font=(self.face, 9), background="#f5f5f5", borderwidth=0)
        style.configure("TEntry", fieldbackground=self.WHITE, bordercolor="#cfcfcf", padding=7)
        style.map("TEntry", bordercolor=[("focus", self.INK)])
        style.configure("TCombobox", padding=7, fieldbackground=self.WHITE, bordercolor="#cfcfcf", arrowsize=12)
        style.map("TCombobox", fieldbackground=[("readonly", self.WHITE)])
        style.configure("TCheckbutton", background=self.BG, padding=(0, 5), focuscolor=self.INK)
        style.configure("White.TCheckbutton", background=self.WHITE, font=(self.face, 9))
        style.map("White.TCheckbutton", background=[("active", self.WHITE)])
        style.configure("TPanedwindow", background=self.BG, sashwidth=12)
        style.configure("Vertical.TScrollbar", background="#dedede", troughcolor=self.WHITE,
                        borderwidth=0, arrowsize=10)
        style.configure("Activity.Horizontal.TProgressbar", background=self.INK, troughcolor=self.LINE,
                        borderwidth=0, thickness=3)

    def _nav_button(self, parent, text, command):
        button = tk.Button(parent, text=text, anchor="w", command=command, bg=self.BG, fg=self.MUTED,
                           activebackground="#e9e9e9", activeforeground=self.INK, relief="flat", bd=0,
                           padx=14, pady=6, cursor="hand2", highlightthickness=1,
                           highlightbackground=self.BG, highlightcolor=self.INK, takefocus=True)
        button.pack(fill="x", pady=2)
        return button

    def _panel(self, parent):
        return tk.Frame(parent, bg=self.WHITE, highlightbackground=self.LINE, highlightthickness=1)

    def _panel_header(self, parent, title):
        header = tk.Frame(parent, bg=self.WHITE, padx=14, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text=title, bg=self.WHITE, fg=self.INK, font=(self.face, 12)).pack(side="left", padx=4)
        return header

    def _text_with_scroll(self, parent):
        frame = tk.Frame(parent, bg=self.WHITE)
        frame.grid(row=1, column=0, sticky="nsew", padx=(8, 6))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word", font=(self.face, 11), undo=True, padx=10, pady=10,
                       bd=0, highlightthickness=0, bg=self.WHITE, fg=self.INK, insertbackground=self.INK,
                       selectbackground="#dce6ef", selectforeground=self.INK, spacing1=3, spacing3=6, width=1, height=1)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        return text

    def _add_empty_state(self, text, title, description):
        empty = tk.Frame(text, bg=self.WHITE)
        tk.Label(empty, text=title, bg=self.WHITE, fg=self.INK, font=(self.face, 13),
                 wraplength=225, justify="left").pack(anchor="w", pady=(0, 10))
        tk.Label(empty, text=description, bg=self.WHITE, fg=self.MUTED, font=(self.face, 10),
                 wraplength=225, justify="left").pack(anchor="w")
        self._placeholders[text] = empty
        text.bind("<Configure>", lambda event: self._refresh_empty_states(), add="+")
        for widget in (empty, *empty.winfo_children()):
            widget.bind("<Button-1>", lambda event, target=text: target.focus_set())
        empty.place(relx=0.5, rely=0.32, anchor="center", width=225)

    def _refresh_empty_states(self):
        if getattr(self, "_closing", False):
            return
        for text, empty in self._placeholders.items():
            if not text.winfo_exists() or not empty.winfo_exists():
                continue
            description = empty.winfo_children()[1]
            if text.winfo_height() < 160:
                description.pack_forget()
            elif not description.winfo_manager():
                description.pack(anchor="w")
            if text.get("1.0", "end").strip() or (text is self.transcript and self.focus_get() is text):
                empty.place_forget()
            else:
                empty.place(relx=0.5, rely=0.5 if text.winfo_height() < 250 else 0.32,
                            anchor="center", width=225)

    def _transcript_modified(self, event=None):
        if not self.transcript.edit_modified():
            return
        self.transcript.edit_modified(False)
        words = len(self.transcript.get("1.0", "end").split())
        self.transcript_count.set(f"{words:,} {'word' if words == 1 else 'words'}")
        if words and self._source.get() == "No audio added":
            self._source.set("Pasted or typed text")
        self._refresh_empty_states()
        self._sync_controls()

    def _initial_split(self):
        self.update_idletasks()
        if self.panes.winfo_width() > 100:
            self.panes.sashpos(0, int(self.panes.winfo_width() * 0.43))

    def show_workspace(self):
        self._view = "workspace"
        self.settings_panel.grid_remove() if hasattr(self, "settings_panel") else None
        self.workspace.grid()
        self.workspace_nav.configure(bg="#e9e9e9", fg=self.INK)
        self.settings_nav.configure(bg=self.BG, fg=self.MUTED)

    def show_settings(self):
        self._view = "settings"
        self.workspace.grid_remove()
        self.settings_panel.grid(row=0, column=0, sticky="nsew")
        self.workspace_nav.configure(bg=self.BG, fg=self.MUTED)
        self.settings_nav.configure(bg="#e9e9e9", fg=self.INK)

    def _build_settings(self):
        self.settings_panel = tk.Frame(self.content, bg=self.BG)
        self.settings_panel.grid_columnconfigure(0, weight=1)
        self.settings_panel.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(self.settings_panel, bg=self.BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.settings_panel, command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)
        body = tk.Frame(canvas, bg=self.BG)
        body.grid_columnconfigure(0, weight=1)
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        tk.Label(body, text="Settings", bg=self.BG, fg=self.INK,
                 font=(self.face, 24)).grid(row=0, column=0, sticky="w")
        tk.Label(body, text="Your models, preferences, and screen privacy.", bg=self.BG,
                 fg=self.MUTED, font=(self.face, 11)).grid(row=1, column=0, sticky="w", pady=(5, 20))
        form = tk.Frame(body, bg=self.WHITE, padx=24, pady=20,
                        highlightbackground=self.LINE, highlightthickness=1)
        form.grid(row=2, column=0, sticky="new")
        form.grid_columnconfigure(0, weight=1)
        provider_frame = tk.Frame(form, bg=self.WHITE)
        provider_frame.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        provider_frame.grid_columnconfigure(0, weight=1)
        tk.Label(provider_frame, text="Answer provider", bg=self.WHITE, fg=self.INK).grid(row=0, column=0, sticky="w")
        self.provider_box = ttk.Combobox(provider_frame, textvariable=self.provider_var,
                                         values=list(LABELS.values()), state="readonly")
        self.provider_box.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.provider_box.bind("<<ComboboxSelected>>", self._provider_changed)
        self.provider_description = tk.StringVar()
        tk.Label(provider_frame, textvariable=self.provider_description, bg=self.WHITE,
                 fg=self.MUTED, wraplength=580, justify="left", anchor="w").grid(row=2, column=0, sticky="ew")
        self.key_frame = tk.Frame(provider_frame, bg=self.WHITE)
        self.key_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.key_frame.grid_columnconfigure(0, weight=1)
        tk.Label(self.key_frame, text="Groq API key", bg=self.WHITE, fg=self.INK).grid(row=0, column=0, sticky="w")
        self.key_entry = ttk.Entry(self.key_frame, textvariable=self.groq_key_var, show="*")
        self.key_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.key_save = ttk.Button(self.key_frame, text="Save key securely", command=self._save_groq_key)
        self.key_save.grid(row=1, column=1, padx=(12, 0), pady=(6, 0))
        tk.Label(self.key_frame, text="Used for this session immediately. Save encrypts it with your Windows account. Clear and save to forget it.",
                 bg=self.WHITE, fg=self.MUTED, wraplength=580, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        # Keep the provider card above the existing model and audio controls.
        original_form = form
        form = tk.Frame(original_form, bg=self.WHITE)
        form.grid(row=1, column=0, sticky="ew")
        form.grid_columnconfigure(0, weight=1)
        self._update_provider_description()
        self._field_label(form, "Answer model", 0)
        model_row = tk.Frame(form, bg=self.WHITE)
        model_row.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        model_row.grid_columnconfigure(0, weight=1)
        self.model_box = ttk.Combobox(model_row, textvariable=self.model_var, state="normal", width=24)
        self.model_box.grid(row=0, column=0, sticky="ew")
        self.model_box.bind("<<ComboboxSelected>>", self._model_changed)
        self.model_box.bind("<FocusOut>", self._model_changed)
        ttk.Button(model_row, text="Check connection", command=self.refresh_models).grid(row=0, column=1, padx=(12, 0))
        tk.Label(form, textvariable=self.engine_detail, bg=self.WHITE, fg=self.MUTED, wraplength=600,
                 justify="left", anchor="w", font=(self.face, 10)).grid(row=2, column=0, sticky="ew", pady=(2, 18))
        self._field_label(form, "Speech recognition", 3)
        speech = tk.Frame(form, bg=self.WHITE)
        speech.grid(row=4, column=0, sticky="ew", pady=(8, 18))
        speech.grid_columnconfigure(1, weight=1)
        self.speech_model_box = ttk.Combobox(speech, textvariable=self.whisper_var, state="readonly", width=12,
                                             values=SPEECH_MODELS)
        self.speech_model_box.grid(row=0, column=0, sticky="w")
        self.speech_model_box.bind("<<ComboboxSelected>>", lambda event: self._save_web_preference())
        tk.Label(speech, text="Small.en favors English accuracy. Tiny is faster but less accurate.", bg=self.WHITE,
                 fg=self.MUTED, wraplength=380, justify="left", font=(self.face, 10)).grid(row=0, column=1, sticky="w", padx=14)
        ttk.Checkbutton(speech, text="Fast transcription (turn off for difficult audio)",
                        variable=self.fast_transcription, command=self._save_web_preference, style="White.TCheckbutton").grid(
                            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        tk.Label(speech, text="Spoken language", bg=self.WHITE, fg=self.INK).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.speech_language_box = ttk.Combobox(speech, textvariable=self.speech_language,
                                                values=list(LANGUAGES), state="readonly", width=16)
        self.speech_language_box.grid(row=2, column=1, sticky="w", pady=(8, 0), padx=14)
        self.speech_language_box.bind("<<ComboboxSelected>>", lambda event: self._save_web_preference())
        tk.Label(speech, textvariable=self.speech_feedback, bg=self.WHITE, fg=self.MUTED,
                 wraplength=560, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._field_label(form, "Audio title (optional)", 5)
        ttk.Entry(form, textvariable=self.title_var).grid(row=6, column=0, sticky="ew", pady=(8, 18))
        ttk.Checkbutton(form, text="Answer automatically after transcription", variable=self.auto_answer,
                        style="White.TCheckbutton").grid(row=7, column=0, sticky="w", pady=(0, 10))
        ttk.Separator(form).grid(row=8, column=0, sticky="ew", pady=(0, 12))
        self.capture_toggle = ttk.Checkbutton(form, text="Exclude this window from screen capture",
                                             variable=self.capture_excluded, command=self._apply_capture_exclusion,
                                             style="White.TCheckbutton")
        self.capture_toggle.grid(row=9, column=0, sticky="w")
        if sys.platform == "win32":
            ttk.Button(form, text="Hide taskbar button", command=self.hide_to_tray).grid(
                row=9, column=0, sticky="e")
        tk.Label(form, textvariable=self.capture_status, bg=self.WHITE, fg=self.MUTED, wraplength=600,
                 justify="left", font=(self.face, 10)).grid(row=10, column=0, sticky="w", pady=(4, 4))
        tk.Label(form, text="Applies to the main window in compatible Windows capture tools. Test before sharing.",
                 bg=self.WHITE, fg=self.MUTED, wraplength=600, justify="left", font=(self.face, 9)).grid(row=11, column=0, sticky="w")
        ttk.Separator(form).grid(row=12, column=0, sticky="ew", pady=(16, 8))
        ttk.Checkbutton(form, text="Allow automatic web search", variable=self.allow_web,
                        style="White.TCheckbutton", command=self._save_web_preference).grid(row=13, column=0, sticky="w")
        tk.Label(form, text="Short search queries may include your question or relevant context. Audio files are not uploaded.",
                 bg=self.WHITE, fg=self.MUTED, wraplength=600, justify="left", font=(self.face, 9)).grid(row=14, column=0, sticky="w", pady=(4, 0))
        if sys.platform != "win32":
            self.capture_toggle.state(["disabled"])
            self.capture_status.set("Unavailable on this platform")
        tk.Label(body, text="Changes apply immediately.   Ctrl+, opens settings.   Esc returns to your workspace.",
                 bg=self.BG, fg=self.MUTED, font=(self.face, 9), wraplength=600, justify="left").grid(row=3, column=0, sticky="w", pady=14)
        def wheel(event):
            if canvas.bbox("all")[3] > canvas.winfo_height():
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
        def bind_wheel(widget):
            widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(body)
        canvas.bind("<MouseWheel>", wheel)

    def _field_label(self, parent, text, row):
        tk.Label(parent, text=text, bg=self.WHITE, fg=self.INK,
                 font=(self.face, 11)).grid(row=row, column=0, sticky="w")

    def _save_web_preference(self):
        try:
            self._provider_models[self._selected_provider] = self.model_var.get().strip()
            temporary = self._preferences_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({"allow_web": self.allow_web.get(),
                                            "provider": self._selected_provider,
                                            "models": self._provider_models,
                                            "speech_model": self.whisper_var.get(),
                                            "speech_language": self.speech_language.get(),
                                            "fast_transcription": self.fast_transcription.get()}), encoding="utf-8")
            temporary.replace(self._preferences_file)
        except OSError:
            self.set_status("Could not save Settings. Changes apply to this session only.")

    def _update_provider_description(self):
        provider = self._selected_provider
        self.provider_description.set({
            "codex": "Uses your ChatGPT sign-in and Codex subscription limits. Questions, included transcript, and recent chat go to OpenAI. Speech is transcribed locally.",
            "groq": "Fast online answers using your Groq key. Questions, included transcript, and recent chat go to Groq; account limits apply.",
            "ollama": "Offline answers on this computer. Web search is disabled. Download answer and speech models before going offline.",
        }[provider])
        self.key_frame.grid() if provider == "groq" else self.key_frame.grid_remove()

    def _provider_changed(self, event=None):
        if self.busy or self.recording:
            self.provider_var.set(LABELS[self._selected_provider])
            return
        self._provider_models[self._selected_provider] = self.model_var.get().strip()
        self._selected_provider = next(k for k, v in LABELS.items() if v == self.provider_var.get())
        self.model_var.set(self._provider_models[self._selected_provider])
        self.model_box["values"] = [DEFAULTS[self._selected_provider]]
        self._history = []
        self._history_context = None
        self._update_provider_description()
        self._save_web_preference()
        self.refresh_models()
        self.set_status(f"Using {self.provider_var.get()}. Chat history reset; transcript kept as context.")

    def _model_changed(self, event=None):
        self._save_web_preference()
        if self._selected_provider == "ollama":
            self._preload_model(self.model_var.get())

    def _save_groq_key(self):
        try:
            save_key(self.groq_key_var.get())
            self.set_status("Groq key encrypted and saved." if self.groq_key_var.get().strip() else "Saved Groq key removed.")
        except (OSError, RuntimeError) as error:
            self.set_status(str(error))

    def _choose_question(self, question):
        self.question_var.set(question)
        self.question_entry.focus_set()

    def _submit_question(self, event=None):
        self.question_entry._push()
        self.generate()
        return "break"

    def _question_newline(self, event=None):
        self.question_entry.insert("insert", "\n")
        self.question_entry._push()
        return "break"

    def clear_transcript(self):
        if self.busy or self.recording or not self.transcript.get("1.0", "end").strip():
            return
        if messagebox.askyesno("Clear transcript?", "This removes the current transcript. Your answer will remain available to copy or save.", parent=self):
            self.transcript.delete("1.0", "end")
            self._last_audio = None
            self._retry_action = None
            self._dismiss_error()
            self._source.set("No audio added")
            self.stage.set("Ready to record")
            self.set_status("Transcript cleared. Record or open another audio file.")

    def _sync_controls(self):
        has_text = bool(self.transcript.get("1.0", "end").strip())
        has_answer = bool(self.answer.get("1.0", "end").strip())
        locked = self.busy or self.recording
        self.provider_box.configure(state="disabled" if locked else "readonly")
        self.model_box.configure(state="disabled" if locked else "normal")
        self.key_entry.configure(state="disabled" if locked else "normal")
        self.key_save.configure(state="disabled" if locked else "normal")
        self.speech_model_box.configure(state="disabled" if locked else "readonly")
        self.speech_language_box.configure(state="disabled" if locked else "readonly")
        can_ask = bool(self.question_var.get().strip()) or has_text
        self.transcript.configure(state="disabled" if locked else "normal")
        self.question_entry.configure(state="disabled" if locked else "normal")
        for button in self.suggestion_buttons:
            button.configure(state="disabled" if locked else "normal")
        self.import_btn.configure(state="disabled" if locked else "normal")
        self.gen_btn.configure(state="normal" if can_ask and not locked else "disabled")
        self.new_chat_btn.configure(state="disabled" if locked else "normal")
        self.clear_btn.configure(state="normal" if has_text and not locked else "disabled")
        self.rec_btn.configure(state="disabled" if self.busy else "normal",
                               style="Recording.TButton" if self.recording else "TButton")
        self.gen_btn.configure(style="Primary.TButton")
        for button in (self.copy_btn, self.save_btn):
            button.configure(state="normal" if has_answer and not self.busy else "disabled")

    def _paint_input_level(self):
        canvas = self.level_canvas
        canvas.delete("all")
        if not self.recording:
            canvas.create_line(0, 12, 168, 12, fill="#d4d4d4", width=1)
            return
        level = max(0.0, min(1.0, self._audio_level))
        for i, factor in enumerate([0.35, 0.55, 0.8, 0.65, 1, 0.75, 0.5, 0.85, 0.6, 0.4, 0.7, 0.3]):
            height = max(2, int(22 * level * factor))
            canvas.create_line(4+i*14, 12-height/2, 4+i*14, 12+height/2, fill=self.BLUE, width=4)

    def _privacy_changed(self):
        value = self.capture_status.get()
        self.privacy_summary.set("Capture exclusion on" if value.startswith("Exclusion enabled") else
                                 "Capture exclusion off" if value == "Exclusion disabled" else "Capture exclusion unavailable")

    def _write_answer(self, text, replace=False):
        self.answer.configure(state="normal")
        if replace:
            self.answer.delete("1.0", "end")
            for tag in self.answer.tag_names():
                if tag.startswith("source-"):
                    self.answer.tag_delete(tag)
        self.answer.insert("end", text)
        self.answer.configure(state="disabled")
        if not getattr(self, "_format_pending", None):
            self._format_pending = self.after(80, self._format_answer)
        self.answer.see("end")
        self._refresh_empty_states()

    def _show_sources(self, sources):
        self._write_answer("\n\nSearch sources\n")
        for index, source in enumerate(sources, 1):
            self._write_answer(f"[{index}] {source.title}\n")
            start = self.answer.index("end-1c")
            self._write_answer(source.url + "\n\n")
            tag = f"source-{index}"
            self.answer.tag_add(tag, start, f"{start}+{len(source.url)}c")
            self.answer.tag_configure(tag, foreground=self.BLUE, underline=True)
            self.answer.tag_bind(tag, "<Button-1>", lambda event, url=source.url: webbrowser.open(url))
            self.answer.tag_bind(tag, "<Enter>", lambda event: self.answer.configure(cursor="hand2"))
            self.answer.tag_bind(tag, "<Leave>", lambda event: self.answer.configure(cursor="xterm"))
        self.answer.yview_moveto(0)

    def _format_answer(self):
        if getattr(self, "_format_pending", None):
            self.after_cancel(self._format_pending)
            self._format_pending = None
        if not getattr(self, "_closing", False):
            self._code_ranges = format_answer(self.answer, self.face, webbrowser.open)

    def _answer_menu(self, event):
        self._format_answer()
        location = self.answer.index(f"@{event.x},{event.y}")
        menu = tk.Menu(self, tearoff=False)
        if self.answer.tag_ranges("sel"):
            menu.add_command(label="Copy selection", command=lambda: self.answer.event_generate("<<Copy>>"))
        for start, end in getattr(self, "_code_ranges", []):
            if self.answer.compare(location, ">=", f"1.0+{start}c") and self.answer.compare(location, "<", f"1.0+{end}c"):
                def copy_code(first=start, last=end):
                    self.clipboard_clear()
                    self.clipboard_append(self.answer.get(f"1.0+{first}c", f"1.0+{last}c"))
                    self.set_status("Code copied with indentation preserved.")
                menu.add_command(label="Copy code", command=copy_code)
                break
        menu.add_command(label="Copy answer as Markdown", command=self.copy_answer)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def new_chat(self):
        if self.busy or self.recording:
            return
        if (self._history or self.answer.get("1.0", "end").strip()) and not messagebox.askyesno(
            "Start a new chat?", "Clear the conversation, answer, and optional audio context?", parent=self
        ):
            return
        self._history = []
        self._history_context = None
        self._retry_action = None
        self._write_answer("", replace=True)
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self._last_audio = None
        self._source.set("No audio added")
        self.question_var.set("")
        self._dismiss_error()
        self._sync_controls()
        self.stage.set("Ready for a question")
        self.set_status("New chat started. Ask anything, or use your transcript as context.")
        self.question_entry.focus_set()

    def _show_error(self, message):
        self.error_message.set(message)
        self.retry_btn.configure(state="normal" if self._retry_action else "disabled")
        self.error_frame.grid()
        self.show_workspace()
        self.stage.set("Needs attention")
        self.set_status("Something went wrong. Review the message above or try again.")

    def _dismiss_error(self):
        self.error_frame.grid_remove()

    def retry_last_action(self):
        if not self.busy and not self.recording and self._retry_action:
            self._dismiss_error()
            self._retry_action()
