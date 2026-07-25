"""Interactive prompts with shell-style TAB path completion."""

import glob
import os
import re
from contextlib import contextmanager
from pathlib import Path

from rich.prompt import Prompt

from .utils import console

# ANSI SGR sequences must be hidden from readline's column arithmetic, otherwise
# the cursor lands in the wrong place after a completion redisplay.
_ANSI_RE = re.compile(r"(\x1b\[[0-9;]*m)")


def complete_path(text: str, dirs_only: bool = False) -> list[str]:
    """Return the filesystem completions for *text*, shell style.

    Directories come back with a trailing separator, and a leading ``~`` is
    preserved so the completed value stays tilde-relative.
    """
    expanded = os.path.expanduser(text)
    matches = glob.glob(expanded + "*")

    if dirs_only:
        matches = [m for m in matches if os.path.isdir(m)]

    matches = [m + os.sep if os.path.isdir(m) else m for m in matches]

    if text.startswith("~"):
        home = str(Path.home())
        matches = [
            "~" + m[len(home):] if m.startswith(home) else m
            for m in matches
        ]

    return sorted(matches)


@contextmanager
def _path_completion(dirs_only: bool = False):
    """Install a path completer on readline for the duration of one prompt.

    ``readline`` is imported lazily: importing it changes ``input()`` behaviour
    process-wide, which should not happen just because some other command was
    run.  Yields ``True`` when completion is active, ``False`` when readline is
    unavailable (no completion, prompt still works).
    """
    try:
        import readline
    except ImportError:
        yield False
        return

    matches: list[str] = []

    def completer(text: str, state: int):
        nonlocal matches
        if state == 0:
            # Delims are "\n" (see below), so `text` is the whole line and each
            # match replaces it entirely.  rstrip() absorbs any stray trailing
            # space.
            matches = complete_path(text.rstrip(), dirs_only=dirs_only)
            if len(matches) == 1 and matches[0].endswith(os.sep):
                # readline appends a space after a *unique* match and Python
                # exposes no way to turn that off.  For a directory that would
                # strand the cursor behind a space; duplicating the match makes
                # it non-unique, so the inserted text is exactly the path and
                # the next segment can be typed straight away, shell style.
                # Files keep the space, which is what a shell does too.
                matches = matches * 2
        return matches[state] if state < len(matches) else None

    prev_completer = readline.get_completer()
    prev_delims = readline.get_completer_delims()

    # Breaking words on "\n" only (never present in a line) makes the whole line
    # the completion word.  The default delims include "/", "~" and "-", which
    # would hand the completer useless fragments; this also lets paths with
    # spaces complete correctly.
    readline.set_completer_delims("\n")
    readline.set_completer(completer)

    # uv-managed CPython links libedit, which needs its own binding syntax.
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    try:
        yield True
    finally:
        readline.set_completer(prev_completer)
        readline.set_completer_delims(prev_delims)


class PathPrompt(Prompt):
    """A :class:`rich.prompt.Prompt` whose input line completes paths on TAB."""

    dirs_only: bool = False

    @classmethod
    def get_input(cls, console, prompt, password: bool, stream=None) -> str:
        if password or stream is not None:
            return super().get_input(console, prompt, password, stream=stream)

        # Hand the rendered prompt to input() rather than printing it first:
        # readline needs to know the prompt to redraw the line after listing
        # matches, otherwise the prompt vanishes on the first ambiguous TAB.
        with console.capture() as capture:
            console.print(prompt, end="")
        rendered = _ANSI_RE.sub("\x01\\1\x02", capture.get())

        with _path_completion(dirs_only=cls.dirs_only):
            return input(rendered)


class _DirPrompt(PathPrompt):
    dirs_only = True


def ask_path(message: str, *, default: str, dirs_only: bool = True) -> str:
    """Ask for a filesystem path, completing it with TAB like a shell does.

    Trailing whitespace and a trailing separator are stripped, since TAB
    completion makes both common and the value is stored as-is in pow.toml.
    """
    prompt_cls = _DirPrompt if dirs_only else PathPrompt
    value = prompt_cls.ask(message, default=default, console=console).strip()

    if len(value) > 1:
        value = value.rstrip(os.sep)

    return value
