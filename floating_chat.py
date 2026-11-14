"""Compact, always-on-top chat surface sharing the workspace's provider flow."""
import tkinter as tk
from answer_formatting import format_answer
import webbrowser
import ctypes
from ctypes import wintypes
import sys
import time


class FloatingChat:
    def __init__(self, app):
        self.app = app
        self._animation = None
        self._detail = False
        self.window = tk.Toplevel(app)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.configure(bg='#211C18')
        self.toolbar = tk.Frame(self.window, bg='#211C18')
        self.toolbar.pack(fill='x', padx=12, pady=8)
        self.new_button = self.icon(self.toolbar, 'compose', self.new_chat)
        self.new_button.pack(side='left')
        self.record_button = self.icon(self.toolbar, 'audio', self.record)
        self.record_button.pack(side='left', padx=(6, 0))
        self.title = tk.Label(self.toolbar, text='Mocha', bg='#211C18', fg='#F4E8DA',
                              font=('Segoe UI', 11, 'bold'))
        self.expand_button = self.icon(self.toolbar, 'expand', app._restore_full_window)
        self.close_button = self.icon(self.toolbar, 'close', self.hide)
        self.body = tk.Frame(self.window, bg='#211C18')
        self.answer = tk.Text(self.body, bg='#211C18', fg='#F4E8DA', relief='flat',
                              wrap='word', height=1, width=1, font=('Segoe UI', 11), padx=12, pady=12,
                              insertbackground='white', state='disabled')
        self.answer.pack(fill='both', expand=True, padx=6)
        self.question = tk.Label(self.body, bg='#302720', fg='#F4E8DA', anchor='w',
                                 justify='left', wraplength=350, padx=12, pady=10,
                                 font=('Segoe UI', 10))
        self.status = tk.Label(self.body, bg='#211C18', fg='#BBA895', anchor='w',
                               wraplength=370, font=('Segoe UI', 9))
        self.status.pack(fill='x', padx=12)
        composer = tk.Frame(self.body, bg='#302720', height=52)
        self.composer = composer
        composer.pack(fill='x', padx=10, pady=10)
        composer.pack_propagate(False)
        self.icon(composer, 'plus', self.new_chat, '#302720').pack(side='left', padx=(6, 0), pady=7)
        self.entry = tk.Entry(composer, bg='#302720', fg='white', relief='flat',
                              disabledbackground='#302720', disabledforeground='#BBA895',
                              highlightthickness=0, bd=0, selectbackground='#805637',
                              insertbackground='white', width=1, font=('Segoe UI', 11))
        self.entry.pack(side='left', fill='x', expand=True, padx=6, pady=14)
        self.entry.bind('<Return>', self.send)
        self.placeholder = tk.Label(composer, text='Start new chat', bg='#302720',
                                    fg='#BBA895', font=('Segoe UI', 11), cursor='xterm')
        self.placeholder.place(x=52, rely=.5, anchor='w')
        self.placeholder.bind('<Button-1>', lambda event: self.entry.focus_set())
        self.entry.bind('<KeyRelease>', lambda event: self._placeholder())
        self.entry.bind('<FocusIn>', lambda event: self._placeholder())
        self.entry.bind('<FocusOut>', lambda event: self._placeholder())
        self.send_button = self.icon(composer, 'send', self.send, '#302720')
        self.send_button.pack(side='right', padx=7, pady=7)
        self.hint = tk.Label(self.body, text='Ask anything', bg='#211C18', fg='#AF9A86',
                             font=('Segoe UI', 10))
        self.answer.configure(spacing1=3, spacing3=7, selectbackground='#805637',
                              highlightthickness=0, borderwidth=0)
        self.window.bind('<Escape>', lambda event: self.hide())
        self.window.bind('<Leave>', self.leave)
        self.expanded = False
        self.last_answer = None
        self.refresh()

    def _placeholder(self):
        if self.entry.get() or self.entry.focus_get() is self.entry:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=52, rely=.5, anchor='w')

    def panel_position(self, width, height, logo_position=None):
        bubble = self.app._floating_icon
        logo_x, original_y = logo_position or (bubble.winfo_x(), bubble.winfo_y())
        # Keep the logo above the panel, even near the bottom of the screen.
        logo_size = bubble.winfo_width()
        offset = logo_size + 10
        logo_y = max(0, min(original_y, self.app.winfo_screenheight()-48-height-offset))
        if logo_y != original_y:
            bubble.geometry(f'+{logo_x}+{logo_y}')
        x = max(0, min(logo_x+logo_size-width, self.app.winfo_screenwidth()-width))
        return x, logo_y+offset

    def follow_logo(self, x, y):
        if not self.window.winfo_viewable():
            return
        if self._animation:
            self.app.after_cancel(self._animation)
            self._animation = None
        width = 440 if self.expanded else 108
        height = (440 if self._detail else 126) if self.expanded else 54
        left, top = self.panel_position(width, height, (x, y))
        self.window.geometry(f'{width}x{height}+{left}+{top}')
        self.window.update_idletasks()
        self.round_window()

    def resize(self, width, height, animate=True):
        if self._animation:
            self.app.after_cancel(self._animation)
            self._animation = None
        target_x, top = self.panel_position(width, height)
        right = target_x+width
        start_w, start_h = self.window.winfo_width(), self.window.winfo_height()
        started = time.monotonic()
        def frame():
            t = min(1, (time.monotonic()-started)/.18) if animate else 1
            ease = 1-(1-t)**3
            w = round(start_w+(width-start_w)*ease)
            h = round(start_h+(height-start_h)*ease)
            self.window.geometry(f'{w}x{h}+{max(0,right-w)}+{top}')
            self.window.update_idletasks()
            self.round_window()
            self._animation = self.app.after(16, frame) if t < 1 else None
        frame()

    def layout_chat(self):
        detail = bool(self.last_answer or self.app.busy or self.app.recording or self.app.error_message.get())
        self._detail = detail
        if detail:
            self.status.pack(before=self.composer, fill='x', padx=20, pady=(0, 4))
            self.answer.pack(before=self.status, fill='both', expand=True, padx=12)
            if self.question.cget('text'):
                self.question.pack(before=self.answer, fill='x', padx=20, pady=(8, 4))
        else:
            self.answer.pack_forget()
            self.status.pack_forget()
            self.question.pack_forget()
        self.resize(440, 440 if detail else 126, self.window.winfo_viewable())

    def icon(self, parent, kind, command, background='#211C18'):
        canvas = tk.Canvas(parent, width=38, height=38, bg=background,
                           highlightthickness=0, cursor='hand2', takefocus=True)
        color = '#EAD8C4'
        def line(*points):
            canvas.create_line(*points, fill=color, width=2, capstyle='round', joinstyle='round')
        if kind == 'compose':
            line(24, 12, 12, 12, 12, 28, 28, 28, 28, 22)
            line(18, 22, 19, 18, 28, 9, 31, 12, 22, 21, 18, 22)
        elif kind == 'audio':
            for x, half in ((11, 4), (16, 9), (21, 6), (26, 3)):
                line(x, 19-half, x, 19+half)
        elif kind == 'expand':
            line(13, 25, 26, 12); line(17, 12, 26, 12, 26, 21)
        elif kind == 'close':
            line(13, 19, 25, 19)
        elif kind == 'send':
            canvas.create_oval(3, 3, 35, 35, fill='#805637', outline='')
            line(19, 26, 19, 12)
            line(13, 18, 19, 12, 25, 18)
        else:
            line(12, 19, 26, 19); line(19, 12, 19, 26)
        canvas.bind('<Enter>', lambda event: canvas.configure(bg='#44362B'))
        canvas.bind('<Leave>', lambda event: canvas.configure(bg=background))
        canvas.bind('<Button-1>', lambda event: command())
        canvas.bind('<Return>', lambda event: command())
        canvas.bind('<space>', lambda event: command())
        return canvas

    def button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg='#302720', fg='white',
                         activebackground='#383838', activeforeground='white',
                         relief='flat', bd=0, padx=10, pady=6, cursor='hand2',
                         font=('Segoe UI', 14), takefocus=True)

    def show(self, expanded=False):
        # Hover must never reopen a previously dismissed chat.
        if not expanded and self.expanded and self.window.winfo_viewable():
            return
        self.expanded = expanded
        width, height = (440, 126) if self.expanded else (108, 54)
        x, y = self.panel_position(width, height)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        if self.expanded:
            self.new_button.pack_forget()
            self.record_button.pack_forget()
            self.title.pack(side='left', padx=10)
            self.close_button.pack(side='right')
            self.expand_button.pack(side='right')
            self.record_button.pack(side='right', padx=4)
            self.body.pack(fill='both', expand=True)
            self.layout_chat()
        else:
            self.body.pack_forget()
            self.title.pack_forget()
            self.close_button.pack_forget()
            self.expand_button.pack_forget()
            self.record_button.pack_forget()
            self.new_button.pack(side='left')
            self.record_button.pack(side='left', padx=(6, 0))
        self.window.deiconify()
        self.window.update_idletasks()
        self.round_window()
        self.window.lift()
        if self.expanded:
            self.entry.focus_set()
        self.app.after_idle(self.app._apply_capture_exclusion)

    def round_window(self):
        """Clip the floating surface into a pill or a softly rounded chat panel."""
        if sys.platform != 'win32':
            return
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
        user32.SetWindowRgn.restype = ctypes.c_int
        gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.DeleteObject.restype = wintypes.BOOL
        radius = 28 if self.expanded else 54
        region = gdi32.CreateRoundRectRgn(0, 0, self.window.winfo_width()+1,
                                         self.window.winfo_height()+1, radius, radius)
        if region:
            hwnd = user32.GetAncestor(self.window.winfo_id(), 2)
            if not user32.SetWindowRgn(hwnd, region, True):
                gdi32.DeleteObject(region)

    def hide(self):
        if self._animation:
            self.app.after_cancel(self._animation)
            self._animation = None
        self.expanded = False
        self.body.pack_forget()
        self.window.withdraw()

    def leave(self, event):
        def check():
            if getattr(self.app, '_floating_moved', False):
                return
            x, y = self.window.winfo_pointerxy()
            if not self.expanded and not (self.window.winfo_rootx() <= x < self.window.winfo_rootx()+self.window.winfo_width()
                    and self.window.winfo_rooty() <= y < self.window.winfo_rooty()+self.window.winfo_height()):
                self.hide()
        self.app.after(250, check)

    def new_chat(self):
        if not self.app.busy and not self.app.recording:
            self.app.new_chat()
            self.entry.delete(0, 'end')
            self.question.pack_forget()
            self.question.configure(text='')
            self.last_answer = ''
            self._placeholder()
            self.hint.configure(text='Ask anything')
            self.show(True)

    def record(self):
        self.show(True)
        self.app.toggle_record()

    def send(self, event=None):
        if not self.app.busy and not self.app.recording and self.entry.get().strip():
            question = self.entry.get().strip()
            self.app.question_var.set(question)
            self.question.configure(text=question)
            self.hint.configure(text='')
            self.app.generate()
            self.entry.delete(0, 'end')
            self._placeholder()
            self.layout_chat()
        return 'break'

    def refresh(self):
        if self.app._closing:
            return
        text = self.app.answer.get('1.0', 'end-1c')
        if text != self.last_answer:
            self.last_answer = text
            self.answer.configure(state='normal')
            self.answer.delete('1.0', 'end')
            self.answer.insert('1.0', text)
            format_answer(self.answer, 'Segoe UI', webbrowser.open)
            for tag, options in {
                'md-inline-code': dict(background='#3B3027', foreground='#F4E8DA'),
                'code-block': dict(background='#302720', foreground='#F4E8DA'),
                'md-quote': dict(foreground='#C2AC96'),
                'md-table-header': dict(background='#3B3027', foreground='#F4E8DA'),
                'md-table-alt': dict(background='#302720'),
            }.items():
                self.answer.tag_configure(tag, **options)
            self.answer.configure(state='disabled')
            self.answer.see('end')
        locked = self.app.busy or self.app.recording
        self.entry.configure(state='disabled' if locked else 'normal')
        self.send_button.configure(state='disabled' if locked else 'normal')
        self.status.configure(text=self.app.status.get() if locked or self.app.error_message.get() else '')
        detail = bool(text or locked or self.app.error_message.get())
        if self.expanded and detail != self._detail:
            self.layout_chat()
        self.app.after(100, self.refresh)
