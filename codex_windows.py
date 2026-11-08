"""Windows launch adapter for the pinned Codex SDK (0.167.0).

The SDK has no process-creation options. Give only its two launcher modules
a subprocess facade; never modify subprocess.Popen globally or vendor files.
"""
import subprocess
import sys


class HiddenSubprocess:
    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def _options(options):
        if sys.platform == "win32":
            options["creationflags"] = options.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return options

    def Popen(self, *args, **options):
        return subprocess.Popen(*args, **self._options(options))

    def run(self, *args, **options):
        return subprocess.run(*args, **self._options(options))


def hide_codex_console():
    if sys.platform != "win32":
        return
    from openai_codex import client, _runtime_requirements
    facade = HiddenSubprocess()
    client.subprocess = facade
    _runtime_requirements.subprocess = facade
