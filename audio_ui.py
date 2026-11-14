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


class Toggle(tk.Canvas):
    """Modern on/off switch bound to a BooleanVar. Mimics the ttk state() API."""
    ON, OFF, DISABLED = "#805637", "#A28F80", "#D6C9BD"

    def __init__(self, parent, variable, command=None, bg="#FFFCF8"):
        super().__init__(parent, width=40, height=22, bg=bg, bd=0, highlightthickness=2,
                         highlightbackground=bg, highlightcolor="#805637", takefocus=True, cursor="hand2")
        self.variable, self.command, self._disabled = variable, command, False
        self._trace = variable.trace_add("write", lambda *_: self._draw())
        for sequence in ("<Button-1>", "<space>", "<Return>"):
            self.bind(sequence, self._flip)
        self.bind("<Destroy>", self._destroyed)
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        on = bool(self.variable.get())
        color = self.DISABLED if self._disabled else (self.ON if on else self.OFF)
        self.delete("all")
        self.create_oval(1, 1, 21, 21, fill=color, outline=color)
        self.create_oval(19, 1, 39, 21, fill=color, outline=color)
        self.create_rectangle(11, 1, 29, 21, fill=color, outline=color)
        x = 21 if on else 3
        self.create_oval(x, 3, x + 16, 19, fill="#FFFCF8", outline="#FFFCF8")

    def _flip(self, event=None):
        if not self._disabled:
            self.focus_set()
            self.variable.set(not self.variable.get())
            if self.command:
                self.command()
        return "break"

    def state(self, spec=None):
        for item in spec or ():
            if item == "disabled":
                self._disabled = True
            elif item == "!disabled":
                self._disabled = False
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self._draw()
        return ()

    def configure(self, cnf=None, **options):
        if "state" in options:
            self._disabled = options.pop("state") == "disabled"
            self._draw()
        return super().configure(cnf, **options) if (cnf or options) else None
    config = configure

    def _destroyed(self, event):
        if event.widget is self:
            self.variable.trace_remove("write", self._trace)


class AudioWorkspaceUI:
    BG = "#F4EFE9"
    WHITE = "#FFFCF8"
    INK = "#30251F"
    MUTED = "#75665C"
    LINE = "#E5DAD0"
    CONTROL_BORDER = "#D6C5B6"
    PANEL_BORDER = "#E5DAD0"
    SELECTED = "#EFE2D4"
    BLUE = "#805637"
    GREEN = "#15803D"
    RED = "#C62828"
    ACCENT = "#805637"
    ACCENT_DARK = "#503621"
    ACCENT_HOVER = "#68432B"
    ACCENT_SOFT = "#EFE2D4"
    SURFACE_ALT = "#F8F3ED"
    NAV_FG = "#69564A"

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, radius, **options):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2,
                  x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        return canvas.create_polygon(points, smooth=True, **options)

    def _build_ui(self):
        self.configure(background=self.BG)
        families = set(tkfont.families(self))
        self.face = next((f for f in ("Inter", "Segoe UI Variable Text", "Segoe UI") if f in families), "TkDefaultFont")
        self.option_add("*Font", (self.face, 10))
        self.option_add("*TCombobox*Listbox.font", (self.face, 10))
        self._style_widgets()
        self._view = "workspace"
        self._operation = None
        self._audio_level = 0.0
        self._retry_action = None
        self._last_audio = None
        self._placeholders = {}
        self._placeholder_widths = {}
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
        self.api_key_var = self.groq_key_var
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
        if self._selected_provider in ("groq", "gemini"):
            self.api_key_var.set(load_key(self._selected_provider))
        self.engine_status.set(f"Checking {LABELS[self._selected_provider]}...")
        self.engine_detail.set("Checking your selected answer provider.")
        self.answer_mode = tk.StringVar(value="Automatic · web queries may go online." if allowed else "Web access disabled in Settings.")
        self.capture_excluded = tk.BooleanVar(value=sys.platform == "win32")
        self.capture_status = tk.StringVar(value="Waiting for window…")
        self.transcript_count = tk.StringVar(value="0 words")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar: brand, navigation, status.
        rail = tk.Frame(self, bg=self.WHITE, width=184)
        rail.grid(row=0, column=0, rowspan=2, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(8, weight=1)
        tk.Frame(rail, bg=self.LINE, width=1).place(relx=1.0, x=-1, rely=0, relheight=1.0)
        brand = tk.Frame(rail, bg=self.WHITE)
        brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(20, 14))
        mark = tk.Canvas(brand, width=34, height=34, bg=self.WHITE, highlightthickness=0)
        mark.pack(side="left", padx=(0, 10))
        from mocha_logo import draw_mark
        draw_mark(mark, size=34)
        names = tk.Frame(brand, bg=self.WHITE)
        names.pack(side="left")
        tk.Label(names, text="Mocha", bg=self.WHITE, fg=self.INK,
                 font=(self.face, 14, "bold")).pack(anchor="w")
        tk.Label(names, text="Personal assistant", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 8)).pack(anchor="w")
        nav = tk.Frame(rail, bg=self.WHITE)
        nav.grid(row=1, column=0, sticky="ew", padx=8)
        self.workspace_nav = self._nav_button(nav, "Workspace", self.show_workspace)
        self.settings_nav = self._nav_button(nav, "Settings", self.show_settings)
        self.bind("<Control-m>", lambda event: self.collapse_to_icon(), add="+")
        bottom = tk.Frame(rail, bg=self.WHITE)
        bottom.grid(row=9, column=0, sticky="ew", padx=16, pady=(8, 10))
        self.engine_dot = tk.Label(bottom, text="\u25cf", bg=self.WHITE, fg=self.MUTED, font=(self.face, 9))
        self.engine_dot.grid(row=0, column=0, sticky="w", padx=(0, 6))
        tk.Label(bottom, textvariable=self.engine_status, bg=self.WHITE, fg=self.INK,
                 wraplength=120, justify="left", font=(self.face, 10, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(bottom, text="Speech stays local", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 2))
        tk.Label(bottom, textvariable=self.privacy_summary, bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9), wraplength=148, justify="left").grid(row=2, column=0, columnspan=2, sticky="w")
        self.content = tk.Frame(self, bg=self.BG)
        self.content.grid(row=0, column=1, sticky="nsew", padx=28, pady=(28, 12))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.workspace = tk.Frame(self.content, bg=self.BG)
        self.workspace.grid(row=0, column=0, sticky="nsew")
        self.workspace.grid_columnconfigure(0, weight=1)
        self.workspace.grid_rowconfigure(2, weight=1)
        heading = tk.Frame(self.workspace, bg=self.BG)
        heading.grid(row=0, column=0, sticky="ew", pady=(6, 12))
        heading.grid_columnconfigure(0, weight=1)
        titles = tk.Frame(heading, bg=self.BG)
        titles.grid(row=0, column=0, sticky="w")
        tk.Label(titles, text="Assistant workspace", bg=self.BG, fg=self.INK,
                 font=(self.face, 16, "bold")).pack(side="left")
        tk.Label(titles, text="Ask a question, bring audio, or search the web.", bg=self.BG,
                 fg=self.MUTED, font=(self.face, 10)).pack(side="left", padx=(14, 0), pady=(4, 0))
        self.context_btn = ttk.Button(heading, text="Context \u00b7 0 words", command=self.toggle_context, width=0)
        self.context_btn.grid(row=0, column=1, sticky="e", padx=(12, 8))
        self.new_chat_btn = ttk.Button(heading, text="New chat", command=self.new_chat, width=0)
        self.new_chat_btn.grid(row=0, column=2, sticky="e")
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
        self._context_panel = left
        self._context_visible = False
        self.panes.add(right, weight=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)
        for panel in (left, right):
            panel.grid_columnconfigure(0, weight=1)
        left_head = self._panel_header(left, "Context")
        ttk.Button(left_head, text="Hide", style="Quiet.TButton",
                   command=lambda: self._set_context_visible(False)).pack(side="right")
        self.clear_btn = ttk.Button(left_head, text="Clear", style="Quiet.TButton", command=self.clear_transcript)
        self.clear_btn.pack(side="right")
        tk.Label(left_head, textvariable=self.transcript_count, bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).pack(side="right", padx=8)
        self.transcript = self._text_with_scroll(left)
        self._add_empty_state(self.transcript, "Add optional context", "Record or open audio, or paste text and code. You can also ask a question directly.")
        self.transcript.bind("<<Modified>>", self._transcript_modified)
        self.transcript.bind("<FocusIn>", lambda event: self._refresh_empty_states())
        self.transcript.bind("<FocusOut>", lambda event: self._refresh_empty_states())
        note = tk.Frame(left, bg=self.WHITE)
        note.grid(row=2, column=0, sticky="ew", padx=18, pady=10)
        tk.Label(note, textvariable=self._source, bg=self.WHITE, fg=self.INK,
                 font=(self.face, 9), anchor="w").pack(anchor="w")
        tk.Label(note, text="Editable while the assistant is idle", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9), anchor="w").pack(anchor="w")
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
        self._add_empty_state(self.answer, "What can I help with?", "Ask about writing, code, explanations, or a problem. Context and web search are handled automatically.", width=420)
        composer = tk.Frame(right, bg=self.WHITE, padx=18, pady=12)
        composer.grid(row=2, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        top = tk.Frame(composer, bg=self.WHITE)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(1, weight=1)
        suggestions = tk.Frame(top, bg=self.WHITE)
        suggestions.grid(row=0, column=0, sticky="w")
        self.suggestion_buttons = []
        for label, request in [("Summarize", "Summarize the transcript if provided, or our conversation."),
                               ("Explain simply", "Explain the topic in simple terms."),
                               ("Key takeaways", "What are the key takeaways from the transcript or our conversation?")]:
            button = ttk.Button(suggestions, text=label, style="Suggestion.TButton",
                                command=lambda value=request: self._choose_question(value))
            button.pack(side="left", padx=(0, 6))
            self.suggestion_buttons.append(button)
        tk.Label(top, textvariable=self.answer_mode, bg=self.WHITE,
                 fg=self.MUTED, font=(self.face, 9)).grid(row=0, column=1, sticky="e")
        box = tk.Frame(composer, bg=self.WHITE, highlightbackground=self.CONTROL_BORDER,
                       highlightcolor=self.ACCENT, highlightthickness=1)
        box.grid(row=1, column=0, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        self.question_entry = PromptBox(box, self.question_var, font=(self.face, 11), height=2, width=1,
                                        wrap="word", padx=10, pady=8, undo=True, relief="flat", bd=0,
                                        highlightthickness=0, bg=self.WHITE, fg=self.INK,
                                        insertbackground=self.ACCENT)
        self.question_entry.grid(row=0, column=0, sticky="ew")
        self.question_entry.bind("<Return>", self._submit_question)
        self.question_entry.bind("<Shift-Return>", self._question_newline)
        self.question_entry.bind("<FocusIn>", lambda event: box.configure(highlightbackground=self.ACCENT), add="+")
        self.question_entry.bind("<FocusOut>", lambda event: box.configure(highlightbackground=self.CONTROL_BORDER), add="+")
        tools = tk.Frame(box, bg=self.WHITE)
        tools.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        tools.grid_columnconfigure(4, weight=1)
        self.rec_btn = ttk.Button(tools, text="Record audio", command=self.toggle_record)
        self.rec_btn.grid(row=0, column=0)
        self.rec_label = tk.Label(tools, text="00:00", bg=self.WHITE, fg=self.INK, font=("Consolas", 11))
        self.rec_label.grid(row=0, column=1, padx=(10, 6))
        self.level_canvas = tk.Canvas(tools, width=96, height=20, bg=self.WHITE, highlightthickness=0)
        self.level_canvas.grid(row=0, column=2)
        self._paint_input_level()
        self.import_btn = ttk.Button(tools, text="Open audio file\u2026", command=self.open_audio)
        self.import_btn.grid(row=0, column=3, padx=(10, 0))
        self.gen_btn = ttk.Button(tools, text="Send", style="Primary.TButton", command=self.generate, width=6)
        self.gen_btn.grid(row=0, column=5, sticky="e")
        hint = tk.Frame(composer, bg=self.WHITE)
        hint.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        hint.grid_columnconfigure(1, weight=1)
        tk.Label(hint, text="Enter to send \u00b7 Shift+Enter for a new line", bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(hint, textvariable=self.stage, bg=self.WHITE, fg=self.MUTED,
                 font=(self.face, 9)).grid(row=0, column=1, sticky="e")
        self._build_settings()
        footer = tk.Frame(self, bg=self.BG)
        footer.grid(row=1, column=1, sticky="ew", padx=28, pady=(0, 14))
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
        self.question_var.trace_add("write", lambda *_: self._fit_prompt())
        self.transcript_count.trace_add("write", lambda *_: self._sync_context_button())
        self._sync_context_button()
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
        style.configure("TButton", padding=(12, 5), background=self.WHITE, foreground=self.INK,
                        bordercolor=self.CONTROL_BORDER, lightcolor=self.WHITE, darkcolor=self.WHITE,
                        focuscolor=self.ACCENT, borderwidth=1, relief="flat")
        style.map("TButton", background=[("disabled", "#F1F2F7"), ("active", self.SURFACE_ALT)],
                  foreground=[("disabled", "#8A90A5")], bordercolor=[("focus", self.ACCENT)])
        style.configure("Primary.TButton", background=self.ACCENT, foreground=self.WHITE,
                        bordercolor=self.ACCENT, lightcolor=self.ACCENT, darkcolor=self.ACCENT)
        style.map("Primary.TButton", background=[("disabled", "#E5DAD0"), ("active", self.ACCENT_HOVER)],
                  foreground=[("disabled", "#6B7289"), ("!disabled", self.WHITE)],
                  bordercolor=[("disabled", "#E5DAD0"), ("active", self.ACCENT_HOVER)],
                  lightcolor=[("disabled", "#E5DAD0"), ("active", self.ACCENT_HOVER)],
                  darkcolor=[("disabled", "#E5DAD0"), ("active", self.ACCENT_HOVER)])
        style.configure("Recording.TButton", background=self.RED, foreground=self.WHITE,
                        bordercolor=self.RED, lightcolor=self.RED, darkcolor=self.RED)
        style.map("Recording.TButton", background=[("active", "#9F1D1D")], foreground=[("!disabled", self.WHITE)])
        style.configure("Quiet.TButton", borderwidth=0, background=self.WHITE, foreground=self.ACCENT_DARK, padding=(8, 3), width=0)
        style.map("Quiet.TButton", background=[("disabled", self.WHITE), ("active", self.ACCENT_SOFT)],
                  foreground=[("disabled", "#8A90A5")])
        style.configure("Suggestion.TButton", padding=(10, 3), font=(self.face, 9, "bold"), background=self.WHITE,
                        foreground=self.ACCENT_DARK, borderwidth=1, bordercolor=self.CONTROL_BORDER)
        style.map("Suggestion.TButton", background=[("disabled", "#F1F2F7"), ("active", self.ACCENT_SOFT)],
                  foreground=[("disabled", "#8A90A5")])
        style.configure("TEntry", fieldbackground=self.WHITE, bordercolor=self.CONTROL_BORDER,
                        lightcolor=self.WHITE, darkcolor=self.WHITE, borderwidth=1, padding=6)
        style.map("TEntry", bordercolor=[("focus", self.ACCENT)], lightcolor=[("focus", self.ACCENT)])
        style.configure("TCombobox", padding=6, fieldbackground=self.WHITE,
                        background=self.WHITE, bordercolor=self.CONTROL_BORDER,
                        lightcolor=self.WHITE, darkcolor=self.WHITE, borderwidth=1, arrowsize=14,
                        arrowcolor=self.MUTED)
        style.map("TCombobox", fieldbackground=[("readonly", self.WHITE)],
                  foreground=[("readonly", self.INK)], background=[("readonly", self.WHITE)],
                  bordercolor=[("focus", self.ACCENT)])
        style.configure("TCheckbutton", background=self.BG, padding=(0, 5), focuscolor=self.ACCENT)
        style.configure("White.TCheckbutton", background=self.WHITE, font=(self.face, 9))
        style.map("White.TCheckbutton", background=[("active", self.WHITE)])
        style.configure("TSeparator", background=self.LINE)
        style.configure("TPanedwindow", background=self.BG, sashwidth=12)
        style.configure("Sash", sashthickness=12, gripcount=0)
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background="#D3D7E6", troughcolor=self.WHITE,
                            bordercolor=self.WHITE, lightcolor="#D3D7E6", darkcolor="#D3D7E6",
                            borderwidth=0, arrowsize=10)
        style.configure("Activity.Horizontal.TProgressbar", background=self.ACCENT, troughcolor=self.LINE,
                        borderwidth=0, thickness=3)

    def _nav_button(self, parent, text, command):
        button = tk.Button(parent, text=text, anchor="w", command=command, bg=self.WHITE, fg=self.NAV_FG,
                           activebackground=self.ACCENT_SOFT, activeforeground=self.ACCENT_DARK, relief="flat", bd=0,
                           padx=12, pady=7, cursor="hand2", highlightthickness=1,
                           highlightbackground=self.WHITE, highlightcolor=self.ACCENT, takefocus=True,
                           font=(self.face, 10))
        button.pack(fill="x", pady=2)
        return button

    def _set_nav(self, button, active):
        background = self.ACCENT_SOFT if active else self.WHITE
        button.configure(bg=background, highlightbackground=background,
                         fg=self.ACCENT_DARK if active else self.NAV_FG,
                         font=(self.face, 10, "bold" if active else "normal"))

    def _panel(self, parent):
        return tk.Frame(parent, bg=self.WHITE, highlightbackground=self.LINE, highlightthickness=1)

    def _panel_header(self, parent, title):
        header = tk.Frame(parent, bg=self.WHITE, padx=14, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text=title, bg=self.WHITE, fg=self.INK, font=(self.face, 12, "bold")).pack(side="left", padx=4)
        return header

    def _text_with_scroll(self, parent):
        frame = tk.Frame(parent, bg=self.WHITE)
        frame.grid(row=1, column=0, sticky="nsew", padx=(8, 6))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word", font=(self.face, 11), undo=True, padx=10, pady=10,
                       bd=0, highlightthickness=0, bg=self.WHITE, fg=self.INK, insertbackground=self.INK,
                       selectbackground="#DCDFFB", selectforeground=self.INK, spacing1=3, spacing3=6, width=1, height=1)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        return text

    def _add_empty_state(self, text, title, description, width=260):
        empty = tk.Frame(text, bg=self.WHITE)
        icon = tk.Canvas(empty, width=52, height=52, bg=self.WHITE, highlightthickness=0)
        self._round_rect(icon, 0, 0, 52, 52, 16, fill=self.ACCENT_SOFT, outline=self.ACCENT_SOFT)
        for x, half in [(17, 5), (22, 9), (27, 13), (32, 9), (37, 5)]:
            icon.create_line(x, 26-half, x, 26+half, fill=self.ACCENT, width=3, capstyle="round")
        icon.pack(pady=(0, 14))
        tk.Label(empty, text=title, bg=self.WHITE, fg=self.INK, font=(self.face, 14, "bold"),
                 wraplength=width, justify="center").pack(pady=(0, 8))
        tk.Label(empty, text=description, bg=self.WHITE, fg=self.MUTED, font=(self.face, 10),
                 wraplength=width, justify="center").pack()
        self._placeholders[text] = empty
        self._placeholder_widths[text] = width
        text.bind("<Configure>", lambda event: self._refresh_empty_states(), add="+")
        for widget in (empty, *empty.winfo_children()):
            widget.bind("<Button-1>", lambda event, target=text: target.focus_set())
        empty.place(relx=0.5, rely=0.32, anchor="center", width=width)

    def _refresh_empty_states(self):
        if getattr(self, "_closing", False):
            return
        for text, empty in self._placeholders.items():
            if not text.winfo_exists() or not empty.winfo_exists():
                continue
            description = empty.winfo_children()[-1]
            if text.winfo_height() < 200:
                description.pack_forget()
            elif not description.winfo_manager():
                description.pack()
            if text.get("1.0", "end").strip() or (text is self.transcript and self.focus_get() is text):
                empty.place_forget()
            else:
                empty.place(relx=0.5, rely=0.5 if text.winfo_height() < 250 else 0.32,
                            anchor="center", width=self._placeholder_widths.get(text, 260))

    def _transcript_modified(self, event=None):
        if not self.transcript.edit_modified():
            return
        self.transcript.edit_modified(False)
        words = len(self.transcript.get("1.0", "end").split())
        self.transcript_count.set(f"{words:,} {'word' if words == 1 else 'words'}")
        if words and not self._context_visible:
            self._set_context_visible(True)
        if words and self._source.get() == "No audio added":
            self._source.set("Pasted or typed text")
        self._refresh_empty_states()
        self._sync_controls()

    def _initial_split(self):
        self._split_context()

    def _split_context(self):
        self.update_idletasks()
        width = self.panes.winfo_width()
        if self._context_visible and width > 100:
            self.panes.sashpos(0, max(280, min(int(width * 0.64), width - 300)))

    def _set_context_visible(self, visible):
        if visible == self._context_visible:
            return
        self._context_visible = visible
        if visible:
            self.panes.add(self._context_panel, weight=1)
            self.after_idle(self._split_context)
        else:
            self.panes.forget(self._context_panel)
        self._sync_context_button()
        self.after_idle(self._refresh_empty_states)

    def toggle_context(self):
        self._set_context_visible(not self._context_visible)
        if self._context_visible:
            self.transcript.focus_set()

    def _sync_context_button(self):
        if hasattr(self, "context_btn"):
            self.context_btn.configure(text=f"Context \u00b7 {self.transcript_count.get()}",
                                       style="Suggestion.TButton" if self._context_visible else "TButton")

    def _fit_prompt(self):
        try:
            counted = self.question_entry.count("1.0", "end-1c", "displaylines")
            lines = counted[0] if isinstance(counted, (tuple, list)) else (counted or 1)
            self.question_entry.configure(height=max(2, min(6, int(lines))))
        except (tk.TclError, TypeError, ValueError):
            pass

    def show_workspace(self):
        self._view = "workspace"
        self.settings_panel.grid_remove() if hasattr(self, "settings_panel") else None
        self.workspace.grid()
        self._set_nav(self.workspace_nav, True)
        self._set_nav(self.settings_nav, False)

    def show_settings(self):
        self._view = "settings"
        self.workspace.grid_remove()
        self.settings_panel.grid(row=0, column=0, sticky="nsew")
        self._set_nav(self.workspace_nav, False)
        self._set_nav(self.settings_nav, True)

    def _build_settings(self):
        self._wrap_labels = []
        self.settings_panel = tk.Frame(self.content, bg=self.BG)
        self.settings_panel.grid_columnconfigure(0, weight=1)
        self.settings_panel.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(self.settings_panel, bg=self.BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.settings_panel, command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)
        body = tk.Frame(canvas, bg=self.BG)
        body.grid_columnconfigure((0, 1), weight=1, uniform="settings")
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        def resize(event):
            width = min(event.width, 1120)
            canvas.itemconfigure(window, width=width)
            wrap = max(220, (width - 16) // 2 - 48)
            for label, offset in self._wrap_labels:
                label.configure(wraplength=max(140, wrap - offset))
        canvas.bind("<Configure>", resize)
        head = tk.Frame(body, bg=self.BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(6, 14))
        head.grid_columnconfigure(0, weight=1)
        titles = tk.Frame(head, bg=self.BG)
        titles.grid(row=0, column=0, sticky="w")
        tk.Label(titles, text="Settings", bg=self.BG, fg=self.INK,
                 font=(self.face, 16, "bold")).pack(side="left")
        tk.Label(titles, text="Your models, preferences, and screen privacy.", bg=self.BG,
                 fg=self.MUTED, font=(self.face, 10)).pack(side="left", padx=(14, 0), pady=(4, 0))
        ttk.Button(head, text="Back to workspace", command=self.show_workspace, width=0).grid(row=0, column=1, sticky="e")
        left_col = tk.Frame(body, bg=self.BG)
        left_col.grid(row=1, column=0, sticky="new", padx=(0, 8))
        right_col = tk.Frame(body, bg=self.BG)
        right_col.grid(row=1, column=1, sticky="new", padx=(8, 0))

        def card(title, parent):
            outer = tk.Frame(parent, bg=self.WHITE, highlightbackground=self.LINE, highlightthickness=1)
            outer.pack(fill="x", pady=(0, 14))
            outer.grid_columnconfigure(0, weight=1)
            inner = tk.Frame(outer, bg=self.WHITE, padx=20, pady=14)
            inner.grid(row=0, column=0, sticky="ew")
            inner.grid_columnconfigure(0, weight=1)
            tk.Label(inner, text=title, bg=self.WHITE, fg=self.INK,
                     font=(self.face, 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
            content = tk.Frame(inner, bg=self.WHITE)
            content.grid(row=1, column=0, sticky="ew")
            content.grid_columnconfigure(0, weight=1)
            return content

        def note(parent, row, text=None, variable=None, pady=(0, 0)):
            label = tk.Label(parent, text=text, textvariable=variable, bg=self.WHITE, fg=self.MUTED,
                             wraplength=420, justify="left", anchor="w", font=(self.face, 10))
            label.grid(row=row, column=0, sticky="ew", pady=pady)
            self._wrap_labels.append((label, 0))
            return label

        # Card 1: AI model
        ai = card("AI model", left_col)
        provider_frame = tk.Frame(ai, bg=self.WHITE)
        provider_frame.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        provider_frame.grid_columnconfigure(0, weight=1)
        self._field_label(provider_frame, "Answer provider", 0)
        self.provider_box = ttk.Combobox(provider_frame, textvariable=self.provider_var,
                                         values=list(LABELS.values()), state="readonly")
        self.provider_box.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        self.provider_box.bind("<<ComboboxSelected>>", self._provider_changed)
        self.provider_description = tk.StringVar()
        note(provider_frame, 2, variable=self.provider_description)
        self.key_frame = tk.Frame(provider_frame, bg=self.WHITE)
        self.key_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.key_frame.grid_columnconfigure(0, weight=1)
        self.key_heading = tk.StringVar(value="API key")
        tk.Label(self.key_frame, textvariable=self.key_heading, bg=self.WHITE, fg=self.INK,
                 font=(self.face, 10, "bold")).grid(row=0, column=0, sticky="w")
        self.key_entry = ttk.Entry(self.key_frame, textvariable=self.api_key_var, show="*")
        self.key_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.key_save = ttk.Button(self.key_frame, text="Save key securely", command=self._save_provider_key)
        self.key_save.grid(row=1, column=1, padx=(12, 0), pady=(6, 0))
        key_note = tk.Label(self.key_frame, text="Used for this session immediately. Save encrypts it with your Windows account. Clear and save to forget it.",
                            bg=self.WHITE, fg=self.MUTED, wraplength=420, justify="left")
        key_note.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._wrap_labels.append((key_note, 0))
        self._update_provider_description()
        model = tk.Frame(ai, bg=self.WHITE)
        model.grid(row=1, column=0, sticky="ew")
        model.grid_columnconfigure(0, weight=1)
        self._field_label(model, "Answer model", 0)
        model_row = tk.Frame(model, bg=self.WHITE)
        model_row.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        model_row.grid_columnconfigure(0, weight=1)
        self.model_box = ttk.Combobox(model_row, textvariable=self.model_var, state="normal", width=24)
        self.model_box.grid(row=0, column=0, sticky="ew")
        self.model_box.bind("<<ComboboxSelected>>", self._model_changed)
        self.model_box.bind("<FocusOut>", self._model_changed)
        ttk.Button(model_row, text="Check connection", command=self.refresh_models).grid(row=0, column=1, padx=(12, 0))
        note(model, 2, variable=self.engine_detail, pady=(4, 0))

        # Card 2: Speech & audio
        audio = card("Speech & audio", right_col)
        pair = tk.Frame(audio, bg=self.WHITE)
        pair.grid(row=0, column=0, sticky="ew")
        pair.grid_columnconfigure((0, 1), weight=1, uniform="speech")
        left_pick = tk.Frame(pair, bg=self.WHITE)
        left_pick.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        left_pick.grid_columnconfigure(0, weight=1)
        self._field_label(left_pick, "Recognition model", 0)
        self.speech_model_box = ttk.Combobox(left_pick, textvariable=self.whisper_var, state="readonly",
                                             values=SPEECH_MODELS)
        self.speech_model_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.speech_model_box.bind("<<ComboboxSelected>>", lambda event: self._save_web_preference())
        right_pick = tk.Frame(pair, bg=self.WHITE)
        right_pick.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        right_pick.grid_columnconfigure(0, weight=1)
        self._field_label(right_pick, "Spoken language", 0)
        self.speech_language_box = ttk.Combobox(right_pick, textvariable=self.speech_language,
                                                values=list(LANGUAGES), state="readonly")
        self.speech_language_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.speech_language_box.bind("<<ComboboxSelected>>", lambda event: self._save_web_preference())
        note(audio, 1, text="Small.en favors English accuracy. Tiny is faster but less accurate.", pady=(10, 0))
        note(audio, 2, variable=self.speech_feedback, pady=(2, 12))
        self._toggle_row(audio, 3, "Fast transcription", "Turn off for difficult audio.",
                         self.fast_transcription, self._save_web_preference)
        title_box = tk.Frame(audio, bg=self.WHITE)
        title_box.grid(row=4, column=0, sticky="ew", pady=(4, 12))
        title_box.grid_columnconfigure(0, weight=1)
        self._field_label(title_box, "Audio title (optional)", 0)
        ttk.Entry(title_box, textvariable=self.title_var).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._toggle_row(audio, 5, "Answer automatically after transcription",
                         "Reply as soon as your audio has been transcribed.", self.auto_answer)

        # Card 3: Screen privacy
        privacy = card("Screen privacy", right_col)
        self.capture_toggle = self._toggle_row(
            privacy, 0, "Exclude this window from screen capture",
            "Applies to the main window in compatible Windows capture tools. Test before sharing.",
            self.capture_excluded, self._apply_capture_exclusion, divider=False)
        note(privacy, 1, variable=self.capture_status)
        if sys.platform == "win32":
            ttk.Button(privacy, text="Hide taskbar button", command=self.hide_to_tray).grid(
                row=2, column=0, sticky="w", pady=(10, 0))

        # Card 4: Web search
        web = card("Web search", left_col)
        self._toggle_row(web, 0, "Allow automatic web search",
                         "Short search queries may include your question or relevant context. Audio files are not uploaded.",
                         self.allow_web, self._save_web_preference, divider=False)
        if sys.platform != "win32":
            self.capture_toggle.state(["disabled"])
            self.capture_status.set("Unavailable on this platform")
        tk.Label(body, text="Changes apply immediately.   Ctrl+, opens settings.   Esc returns to your workspace.",
                 bg=self.BG, fg=self.MUTED, font=(self.face, 9), wraplength=600, justify="left").grid(
                     row=2, column=0, columnspan=2, sticky="w", pady=6)
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
                 font=(self.face, 10, "bold")).grid(row=row, column=0, sticky="w")

    def _toggle_row(self, parent, row, title, description, variable, command=None, divider=True):
        holder = tk.Frame(parent, bg=self.WHITE)
        holder.grid(row=row, column=0, sticky="ew")
        if divider:
            tk.Frame(holder, bg="#EDEFF6", height=1).pack(fill="x", pady=(0, 12))
        line = tk.Frame(holder, bg=self.WHITE)
        line.pack(fill="x", pady=(0, 10))
        toggle = Toggle(line, variable, command, bg=self.WHITE)
        toggle.pack(side="right", padx=(16, 0))
        text = tk.Frame(line, bg=self.WHITE)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, bg=self.WHITE, fg=self.INK, font=(self.face, 10, "bold"),
                 justify="left", anchor="w").pack(anchor="w")
        detail = tk.Label(text, text=description, bg=self.WHITE, fg=self.MUTED, font=(self.face, 9),
                          wraplength=360, justify="left", anchor="w")
        detail.pack(anchor="w", pady=(2, 0))
        if hasattr(self, "_wrap_labels"):
            self._wrap_labels.append((detail, 76))
        return toggle

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
            "gemini": "Online answers using your Google AI Studio Gemini key. Questions, included transcript, and recent chat go to Google; account limits apply.",
            "ollama": "Offline answers on this computer. Web search is disabled. Download answer and speech models before going offline.",
        }[provider])
        if provider in ("groq", "gemini"):
            self.key_heading.set(f"{LABELS[provider]} API key")
            self.api_key_var.set(load_key(provider))
            self.key_frame.grid()
        else:
            self.key_frame.grid_remove()

    def _provider_changed(self, event=None):
        if self.busy or self.recording:
            self.provider_var.set(LABELS[self._selected_provider])
            return
        self._provider_models[self._selected_provider] = self.model_var.get().strip()
        self._selected_provider = next(k for k, v in LABELS.items() if v == self.provider_var.get())
        if self._selected_provider in ("groq", "gemini"):
            self.api_key_var.set(load_key(self._selected_provider))
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

    def _save_provider_key(self):
        try:
            save_key(self.api_key_var.get(), self._selected_provider)
            name = LABELS[self._selected_provider]
            self.set_status(f"{name} key encrypted and saved." if self.api_key_var.get().strip() else f"Saved {name} key removed.")
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
            canvas.create_line(0, 10, 96, 10, fill="#d4d4d4", width=1)
            return
        level = max(0.0, min(1.0, self._audio_level))
        for i, factor in enumerate([0.35, 0.55, 0.8, 0.65, 1, 0.75, 0.5, 0.85, 0.6, 0.4, 0.7, 0.3]):
            height = max(2, int(18 * level * factor))
            canvas.create_line(4+i*8, 10-height/2, 4+i*8, 10+height/2, fill=self.BLUE, width=3)

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
