"""Markdown presentation for Tk Text; original answer remains intact for export.

No HTML or generated code is executed. Incomplete fences are styled while streaming.
"""
import re
from urllib.parse import urlsplit


def format_answer(widget, face="Segoe UI", open_link=None):
    text = widget.get("1.0", "end-1c")
    for name in widget.tag_names():
        if name.startswith("md-") or name == "code-block":
            widget.tag_delete(name)
    styles = {
        "md-hidden": dict(elide=True),
        "md-bold": dict(font=(face, 11, "bold")),
        "md-italic": dict(font=(face, 11, "italic")),
        "md-bold-italic": dict(font=(face, 11, "bold italic")),
        "md-inline-code": dict(font=("Consolas", 10), background="#f0f2f5"),
        "code-block": dict(font=("Consolas", 10), background="#f2f4f7", foreground="#20252b",
                           lmargin1=12, lmargin2=12, rmargin=12, spacing1=0, spacing2=0,
                           spacing3=0, wrap="none", tabs=("32p",)),
        "md-quote": dict(lmargin1=16, lmargin2=16, foreground="#626262"),
        "md-list": dict(lmargin1=8, lmargin2=26, spacing1=2, spacing3=2),
        "md-table": dict(font=("Consolas", 10), wrap="none", spacing1=0, spacing3=0),
    }
    for level, size in enumerate((19, 16, 14, 12, 11, 11), 1):
        styles[f"md-h{level}"] = dict(font=(face, size, "bold"), spacing1=12, spacing3=7)
    for name, options in styles.items():
        widget.tag_configure(name, **options)

    def tag(name, start, end):
        if end > start:
            widget.tag_add(name, f"1.0+{start}c", f"1.0+{end}c")

    def inline(value, offset):
        # Code spans take priority over emphasis; link labels can contain emphasis.
        pattern = re.compile(r"(?<!\\)(`+)(.+?)\1|(?<!\\)\[([^\]\n]+)\]\(([^\s)]+)\)|"
                             r"(?<![\\\w])(\*\*\*|___|\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\5(?!\w)")
        for match in pattern.finditer(value):
            start, end = offset + match.start(), offset + match.end()
            if match.group(1):
                width = len(match.group(1))
                tag("md-inline-code", start, end)
                tag("md-hidden", start, start + width)
                tag("md-hidden", end - width, end)
            elif match.group(3):
                label, url = match.group(3), match.group(4)
                tag("md-hidden", start, start + 1)
                tag("md-hidden", start + 1 + len(label), end)
                inline(label, start + 1)
                try:
                    parsed = urlsplit(url)
                except ValueError:
                    continue
                if parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username and not parsed.password:
                    name = f"md-link-{start}"
                    widget.tag_configure(name, foreground="#1d5fbf", underline=True)
                    tag(name, start + 1, start + 1 + len(label))
                    if open_link:
                        widget.tag_bind(name, "<Button-1>", lambda event, target=url: open_link(target))
                        widget.tag_bind(name, "<Enter>", lambda event: widget.configure(cursor="hand2"))
                        widget.tag_bind(name, "<Leave>", lambda event: widget.configure(cursor="xterm"))
            else:
                marker, content = match.group(5), match.group(6)
                width = len(marker)
                name = "md-bold-italic" if width == 3 else "md-bold" if width == 2 else "md-italic"
                tag(name, start, end)
                tag("md-hidden", start, start + width)
                tag("md-hidden", end - width, end)
                inline(content, start + width)

    position, fence, code_start = 0, None, 0
    code_ranges = []
    for line in text.splitlines(keepends=True):
        end = position + len(line)
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*?)(?:\r?\n)?$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                tag("code-block", code_start, position)
                code_ranges.append((code_start, position))
                tag("md-hidden", position, end)
                fence = None
            else:
                tag("code-block", position, end)
        elif marker:
            fence, code_start = marker[1], end
            tag("md-hidden", position, end)
        else:
            heading = re.match(r"^( {0,3}#{1,6})[ \t]+", line)
            quote = re.match(r"^ {0,3}>[ \t]?", line)
            bullet = re.match(r"^\s*(?:[-+*]|\d+[.)])[ \t]+", line)
            if heading:
                tag(f"md-h{heading[1].count('#')}", position, end)
                tag("md-hidden", position, position + heading.end())
            elif quote:
                tag("md-quote", position, end)
                tag("md-hidden", position, position + quote.end())
            elif bullet:
                tag("md-list", position, end)
            elif re.match(r"^\s*\|.*\|\s*$", line):
                tag("md-table", position, end)
            inline(line, position)
        position = end
    if fence:
        code_ranges.append((code_start, len(text)))
        tag("code-block", code_start, len(text))
    for level in range(1, 7):
        widget.tag_raise(f"md-h{level}")
    widget.tag_raise("md-inline-code")
    widget.tag_raise("md-hidden")
    return code_ranges
