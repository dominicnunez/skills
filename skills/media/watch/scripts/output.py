"""Render untrusted source text without terminal control interpretation."""
from __future__ import annotations

import argparse
import codecs
import os
import subprocess
import sys


def display_text(value: object) -> str:
    """Visibly encode C0/C1/DEL controls; retain ordinary Unicode, LF and TAB."""
    return "".join(
        f"\\u{ord(char):04x}" if ((ord(char) < 32 and char not in "\n\t") or 127 <= ord(char) < 160) else char
        for char in str(value)
    )


class DisplayParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            super()._print_message(display_text(message), file)


def run_logged(command: list[str]) -> subprocess.CompletedProcess:
    """Stream sanitized child diagnostics with bounded UTF-8 decoding memory."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=environment) as process:
        while chunk := process.stdout.read1(4096):
            sys.stderr.write(display_text(decoder.decode(chunk)))
            sys.stderr.flush()
        sys.stderr.write(display_text(decoder.decode(b"", final=True)))
        sys.stderr.flush()
        return subprocess.CompletedProcess(command, process.wait())
