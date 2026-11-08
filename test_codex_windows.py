import subprocess
import sys
import unittest
from unittest.mock import patch

from codex_windows import HiddenSubprocess, hide_codex_console


class HiddenLaunchTests(unittest.TestCase):
    def test_only_sdk_launchers_are_adapted(self):
        from openai_codex import client, _runtime_requirements
        original = subprocess.Popen
        with patch.object(client, "subprocess"), patch.object(_runtime_requirements, "subprocess"):
            hide_codex_console()
            if sys.platform == "win32":
                self.assertIsInstance(client.subprocess, HiddenSubprocess)
                self.assertIsInstance(_runtime_requirements.subprocess, HiddenSubprocess)
            self.assertIs(subprocess.Popen, original)

    @unittest.skipUnless(sys.platform == "win32", "Windows console flags")
    def test_both_launch_paths_hide_console_and_preserve_options(self):
        facade = HiddenSubprocess()
        for name in ("Popen", "run"):
            with self.subTest(name=name), patch("codex_windows.subprocess." + name) as launch:
                getattr(facade, name)(["codex.exe"], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                                      stdout=subprocess.PIPE, text=True)
                options = launch.call_args.kwargs
                self.assertTrue(options["creationflags"] & subprocess.CREATE_NO_WINDOW)
                self.assertTrue(options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
                self.assertEqual(options["stdout"], subprocess.PIPE)
                self.assertTrue(options["text"])

    @unittest.skipUnless(sys.platform == "win32", "Windows console check")
    def test_real_child_has_no_console_and_pipes_work(self):
        result = HiddenSubprocess().run(
            [sys.executable, "-c", "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "0")


if __name__ == "__main__":
    unittest.main()
