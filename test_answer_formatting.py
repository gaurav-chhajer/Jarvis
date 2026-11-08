import tkinter as tk
import unittest
from answer_formatting import format_answer


class AnswerFormattingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.text = tk.Text(self.root)

    def tearDown(self):
        self.text.destroy()

    def render(self, value):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        return format_answer(self.text)

    def tagged(self, tag):
        ranges = self.text.tag_ranges(tag)
        return [self.text.get(first, last) for first, last in zip(ranges[::2], ranges[1::2])]

    def test_prose_styles_preserve_original_for_export(self):
        original = "## Heading\n\nA **bold** and *italic* word with `some_code`.\n- One\n- Two\n> Quote\n"
        self.render(original)
        for tag in ("md-h2", "md-bold", "md-italic", "md-inline-code", "md-list", "md-quote"):
            self.assertTrue(self.text.tag_ranges(tag), tag)
        self.assertEqual(self.text.get("1.0", "end-1c"), original)
        self.assertEqual(str(self.text.tag_cget("md-hidden", "elide")), "1")

    def test_code_is_literal_and_indentation_is_exact(self):
        original = "```python\ndef add(a, b):\n    return a + b  # **literal**\n```\n"
        ranges = self.render(original)
        first, last = ranges[0]
        self.assertEqual(original[first:last], "def add(a, b):\n    return a + b  # **literal**\n")
        self.assertFalse(self.text.tag_ranges("md-bold"))
        self.assertEqual(self.text.tag_cget("code-block", "wrap"), "none")

    def test_streaming_unclosed_fence_and_repeated_render(self):
        self.render("Start\n~~~js\n    x = 1\n")
        self.assertIn("    x = 1\n", self.tagged("code-block"))
        self.render("Plain text")
        self.assertFalse(self.text.tag_ranges("code-block"))
        self.assertFalse(self.text.tag_ranges("md-hidden"))

    def test_inline_code_does_not_interpret_emphasis_and_identifiers(self):
        self.render("`**literal**` and snake_case_name")
        self.assertFalse(self.text.tag_ranges("md-bold"))
        self.assertFalse(self.text.tag_ranges("md-italic"))

    def test_links_allow_only_http_and_https(self):
        self.render("[Docs](https://docs.python.org/) [Bad](javascript:alert) [Credentials](https://user:pass@example.com)")
        links = [name for name in self.text.tag_names() if name.startswith("md-link-")]
        self.assertEqual(len(links), 1)


if __name__ == "__main__":
    unittest.main()
