"""Interactive prompts: shell-style TAB path completion and an arrow-key picker."""

import glob
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from rich.control import Control
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


# ── Arrow-key single-choice picker ──────────────────────────────────────────────

#: Escape sequences emitted by the arrow keys, plus vim-style aliases.
_KEY_SEQUENCES = {
    "\x1b[A": "up",
    "\x1b[B": "down",
    "\x1bOA": "up",     # application cursor mode
    "\x1bOB": "down",
    "k": "up",
    "j": "down",
    "\r": "enter",
    "\n": "enter",
    "\x03": "abort",    # Ctrl-C
    "\x04": "abort",    # Ctrl-D
    "\x1b": "abort",    # bare Esc
    "q": "abort",
}


@contextmanager
def _cbreak_mode():
    """Put the terminal in cbreak mode for one picker, yielding its fd.

    cbreak rather than raw: it turns off line buffering and echo but leaves the
    *output* flags alone, so newlines still render normally while the menu
    redraws.  The previous settings are always restored, including when the
    body raises - a picker that left the terminal without echo would break the
    user's shell.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def _read_key(fd: int) -> str:
    """Block for one keypress and return a normalised name.

    Reads the raw file descriptor rather than ``sys.stdin``: the text wrapper
    buffers, so a three-byte arrow sequence would be pulled into Python's
    buffer whole and a byte-at-a-time reader could not tell it from a bare Esc.
    In cbreak mode the terminal delivers an escape sequence as a single write,
    so one read returns all of it.

    Args:
        fd: File descriptor of the terminal, as yielded by :func:`_cbreak_mode`.

    Returns:
        One of ``"up"``, ``"down"``, ``"enter"``, ``"abort"``, or ``""`` for a
        key with no meaning here (which the caller ignores).
    """
    data = os.read(fd, 8)
    if not data:  # EOF - treat a vanished terminal as an abort, never spin
        return "abort"
    return _KEY_SEQUENCES.get(data.decode(errors="ignore"), "")


def _is_interactive() -> bool:
    """True when a live terminal can drive the picker."""
    try:
        return console.is_terminal and sys.stdin.isatty()
    except (AttributeError, ValueError):  # detached/closed stdin
        return False


def _render_menu(choices: list[tuple[str, str]], selected: int) -> int:
    """Print the menu block and return how many lines it occupies.

    The caller rewinds by exactly this many lines to redraw in place, so the
    count can never drift out of step with the layout.
    """
    console.print()
    for i, (value, annotation) in enumerate(choices):
        suffix = f" [dim]({annotation})[/dim]" if annotation else ""
        if i == selected:
            console.print(f"   [bold green]\u276f {value}[/bold green]{suffix}", highlight=False)
        else:
            console.print(f"     [dim]{value}[/dim]{suffix}", highlight=False)
    console.print()
    console.print("   [dim]\u2191/\u2193 to move, Enter to confirm[/dim]", highlight=False)

    return len(choices) + 3  # leading blank + choices + trailing blank + hint


def ask_choice(
    message: str,
    choices: list[tuple[str, str]],
    *,
    default: str | None = None,
) -> str:
    """Pick one value from *choices* with the arrow keys.

    *choices* is a list of ``(value, annotation)`` pairs in display order; the
    annotation is shown dimmed after the value and may be empty.  The cursor
    starts on *default* when it is present, otherwise on the first entry.
    *message* labels the fallback prompt below; the menu itself is untitled,
    since the caller has already said what is being chosen.

    Falls back to a typed :class:`rich.prompt.Prompt` when there is no terminal
    to drive (piped stdin, CI, ``TERM=dumb``, the click test runner), so the
    command stays scriptable.

    Raises:
        KeyboardInterrupt: if the user aborts with Ctrl-C, Esc or ``q``.
    """
    if not choices:
        raise ValueError("ask_choice requires at least one choice")

    values = [value for value, _ in choices]
    selected = values.index(default) if default in values else 0

    if not _is_interactive():
        return Prompt.ask(message, choices=values, default=values[selected], console=console)

    # The caller's step header already says what is being chosen, so the menu
    # itself carries no title.
    height = _render_menu(choices, selected)

    try:
        console.show_cursor(False)
        with _cbreak_mode() as fd:
            while True:
                key = _read_key(fd)
                if key == "enter":
                    break
                if key == "abort":
                    raise KeyboardInterrupt
                if key in ("up", "down"):
                    step = -1 if key == "up" else 1
                    selected = (selected + step) % len(choices)
                    console.control(Control.move(0, -height))
                    _render_menu(choices, selected)
    finally:
        console.show_cursor(True)

    return values[selected]
