"""Mocha's vector cup mark and lightweight, state-aware desktop animation."""
import math
import time
import tkinter as tk


def draw_mark(canvas, size=64, phase=0, hover=0, recording=False, busy=False):
    canvas.delete('mocha')
    scale = size / 64
    def oval(box, **kw):
        canvas.create_oval(*(v*scale for v in box), tags='mocha', **kw)
    def line(points, **kw):
        canvas.create_line(*(v*scale for v in points), tags='mocha',
                           capstyle='round', joinstyle='round', **kw)
    ink = '#f2dfca'
    accent = '#d6ac80'
    oval((3, 3, 61, 61), fill='#292522' if hover else '#211f1d',
         outline=accent if hover else '#51463d', width=scale*1.5)
    # Handle sits behind the cup; a warm rim and saucer keep the silhouette crisp.
    oval((38, 30, 51, 43), fill='', outline=ink, width=3*scale)
    canvas.create_polygon(*(v*scale for v in (18, 29, 44, 29, 42, 43, 38, 47,
                                              25, 47, 21, 43)),
                          fill=ink, outline='', smooth=True, tags='mocha')
    oval((20, 28, 43, 34), fill='#76533b', outline=ink, width=2*scale)
    line((19, 50, 44, 50), fill=accent, width=2*scale)
    if recording:
        for i in range(3):
            height = 4+7*(.5+.5*math.sin(phase*3+i*1.7))
            line((25+i*7, 24-height, 25+i*7, 24), fill=accent, width=2*scale)
    else:
        for i in range(3):
            x = 25+i*7
            drift = math.sin(phase+i)*1.6
            line((x, 24, x-2+drift, 20, x+2+drift, 16, x, 12),
                 fill=accent, width=1.5*scale, smooth=True)
    if busy:
        canvas.create_arc(5*scale, 5*scale, 59*scale, 59*scale,
                          start=(phase*65)%360, extent=65, style='arc',
                          outline=accent, width=2*scale, tags='mocha')


class MochaLogo(tk.Canvas):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, width=128, height=128, highlightthickness=0,
                         cursor='hand2', **kwargs)
        self.app = app
        self.hovered = False
        self._timer = None
        self.bind('<Enter>', lambda event: self._hover(True))
        self.bind('<Leave>', lambda event: self._hover(False))
        self.bind('<Destroy>', self._destroyed)
        self._animate()

    def _hover(self, value):
        self.hovered = value

    def _animate(self):
        if getattr(self.app, '_closing', False):
            return
        if self.winfo_viewable():
            draw_mark(self, size=128, phase=time.monotonic()*1.4, hover=self.hovered,
                      recording=self.app.recording, busy=self.app.busy)
        self._timer = self.after(40 if self.winfo_viewable() else 250, self._animate)

    def _destroyed(self, event):
        if event.widget is self and self._timer:
            self.after_cancel(self._timer)
            self._timer = None
