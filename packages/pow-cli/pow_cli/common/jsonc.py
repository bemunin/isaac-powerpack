"""Minimal JSONC reader and in-place patcher.

VSCode settings files allow ``//`` comments, and the ones Isaac Sim ships also
carry a trailing comma, so :func:`json.loads` cannot read them and no
round-tripping JSON library is a dependency of this package.

This module scans the **top level** of a JSONC object and records the byte span
of every entry.  That is enough to replace a value in place, which is what
``pow init`` needs: the keys pow owns are rewritten and the rest of the
document - the user's own settings, their comments, their formatting and key
order - survives byte for byte.  It is the JSON counterpart of what tomlkit
does for ``pow.toml``.
"""

import json
import re
from dataclasses import dataclass


class JsoncError(ValueError):
    """The document is not a JSONC object this module can work with."""


@dataclass(frozen=True)
class Entry:
    """One ``"key": value`` pair at the top level of the document.

    ``entry_start``/``entry_end`` span everything that belongs to the entry -
    the whitespace and comments in front of the key, and the trailing comma
    behind the value - so deleting that slice leaves a well-formed document.
    """

    key: str
    key_start: int
    value_start: int
    value_end: int
    entry_start: int
    entry_end: int


def _skip_ws(text: str, i: int) -> int:
    """Advance past whitespace and comments."""
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                raise JsoncError("unterminated block comment")
            i = j + 2
        else:
            break
    return i


def _scan_string(text: str, i: int) -> int:
    """Return the index just past the string literal starting at *i*."""
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    raise JsoncError("unterminated string")


def _scan_value(text: str, i: int) -> int:
    """Return the index just past the value starting at *i*."""
    n = len(text)
    c = text[i]

    if c == '"':
        return _scan_string(text, i)

    if c in "[{":
        depth = 0
        while i < n:
            i = _skip_ws(text, i)
            if i >= n:
                break
            ch = text[i]
            if ch == '"':
                i = _scan_string(text, i)
                continue
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise JsoncError("unterminated array or object")

    # Scalar: runs until the entry separator, the end of the line or a comment.
    j = i
    while j < n and text[j] not in ",}]\n" and not (
        text[j] == "/" and j + 1 < n and text[j + 1] in "/*"
    ):
        j += 1
    end = len(text[:j].rstrip())
    if end <= i:
        raise JsoncError(f"empty value at offset {i}")
    return end


def scan_top_level(text: str) -> tuple[list[Entry], int]:
    """Scan the root object of *text*.

    Returns the entries in document order and the index of the root's closing
    brace.  Duplicate keys are reported as separate entries, in the order they
    appear.

    Raises:
        JsoncError: the document is not an object, or is malformed.
    """
    i = _skip_ws(text, 0)
    if i >= len(text) or text[i] != "{":
        raise JsoncError("document is not a JSON object")

    i += 1
    n = len(text)
    entries: list[Entry] = []

    while True:
        entry_start = i
        i = _skip_ws(text, i)
        if i >= n:
            raise JsoncError("unterminated object")
        if text[i] == "}":
            return entries, i
        if text[i] == ",":
            i += 1
            continue
        if text[i] != '"':
            raise JsoncError(f"unexpected character {text[i]!r} at offset {i}")

        key_start = i
        key_end = _scan_string(text, i)
        try:
            key = json.loads(text[key_start:key_end])
        except ValueError as e:
            raise JsoncError(f"bad key at offset {key_start}: {e}")

        i = _skip_ws(text, key_end)
        if i >= n or text[i] != ":":
            raise JsoncError(f"missing ':' after key {key!r}")

        i = _skip_ws(text, i + 1)
        if i >= n:
            raise JsoncError(f"missing value for key {key!r}")
        value_start = i
        value_end = _scan_value(text, i)

        i = _skip_ws(text, value_end)
        entry_end = value_end
        if i < n and text[i] == ",":
            entry_end = i + 1
            i = entry_end

        entries.append(Entry(key, key_start, value_start, value_end, entry_start, entry_end))


def strip_jsonc(text: str) -> str:
    """Return *text* as strict JSON: comments and trailing commas removed."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = _scan_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                raise JsoncError("unterminated block comment")
            i = j + 2
            continue
        if c == ",":
            j = _skip_ws(text, i + 1)
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_value(text: str):
    """Parse one JSONC value (comments and trailing commas tolerated)."""
    try:
        return json.loads(strip_jsonc(text))
    except ValueError as e:
        raise JsoncError(f"cannot parse value: {e}")


def render_value(value, indent: int = 4) -> str:
    """Render *value* as JSON, expanded over several lines when it is long.

    Objects are always expanded - a settings.json block of globs reads far
    better one per line - while short arrays stay inline.
    """
    inline = json.dumps(value)
    if not value or not isinstance(value, (list, dict)):
        return inline
    if isinstance(value, list) and indent + len(inline) <= 80:
        return inline

    pad = " " * (indent + 4)
    close_pad = " " * indent
    if isinstance(value, list):
        items = ",\n".join(f"{pad}{json.dumps(v)}" for v in value)
        return f"[\n{items}\n{close_pad}]"
    items = ",\n".join(f"{pad}{json.dumps(k)}: {json.dumps(v)}" for k, v in value.items())
    return f"{{\n{items}\n{close_pad}}}"


def _infer_indent(text: str, entries: list[Entry]) -> int:
    """Indent width used by the document's own top-level entries."""
    if not entries:
        return 4
    line_start = text.rfind("\n", 0, entries[0].key_start) + 1
    prefix = text[line_start:entries[0].key_start]
    return len(prefix) if prefix.isspace() and prefix else 4


def _apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _append_entries(text: str, additions: dict, indent: int) -> str:
    """Insert *additions* just before the root's closing brace."""
    entries, close = scan_top_level(text)

    tail_start = close
    while tail_start > 0 and text[tail_start - 1] in " \t\r\n":
        tail_start -= 1

    head = text[:tail_start]
    if entries and not head.rstrip().endswith(","):
        head += ","

    pad = " " * indent
    rendered = [f"{pad}{json.dumps(k)}: {render_value(v, indent)}" for k, v in additions.items()]
    head += "\n" + ",\n".join(rendered)

    tail = text[tail_start:]
    if "\n" not in text[tail_start:close]:
        tail = "\n" + tail
    return head + tail


def patch(text: str, updates: dict, remove=()) -> tuple[str, dict]:
    """Rewrite only the keys pow owns, leaving the rest of *text* alone.

    * A key in *updates* that already exists has its value replaced in place.
    * Later duplicates of such a key are deleted - the first one wins - which is
      how a ``settings.json`` written by an older pow gets cleaned up.
    * A key in *remove* is deleted (used for keys VSCode has since renamed).
    * A key in *updates* that is absent is appended before the closing brace.

    Returns the new text and ``{key: (old, new)}`` for the values that actually
    changed, with ``old``/``new`` ``None`` when the key was added/removed.  The
    caller decides whether to write: when nothing changed the returned text is
    identical to *text*, so a re-run of ``pow init`` is a true no-op.

    Raises:
        JsoncError: *text* is not a JSONC object.  Nothing is written, so the
            caller can report the error and leave the file as the user left it.
    """
    entries, _ = scan_top_level(text)
    indent = _infer_indent(text, entries)

    changed: dict = {}
    edits: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for entry in entries:
        value_text = text[entry.value_start:entry.value_end]

        if entry.key in remove:
            changed[entry.key] = (parse_value(value_text), None)
            edits.append((entry.entry_start, entry.entry_end, ""))
            continue

        if entry.key not in updates:
            continue

        if entry.key in seen:
            # A duplicate of a key we own: drop it, keeping the first.
            edits.append((entry.entry_start, entry.entry_end, ""))
            continue

        seen.add(entry.key)
        old = parse_value(value_text)
        new = updates[entry.key]
        if old == new:
            continue
        changed[entry.key] = (old, new)
        edits.append((entry.value_start, entry.value_end, render_value(new, indent)))

    patched = _apply_edits(text, edits)

    missing = {key: value for key, value in updates.items() if key not in seen}
    if missing:
        patched = _append_entries(patched, missing, indent)
        for key, value in missing.items():
            changed[key] = (None, value)

    if patched != text:
        # A deletion can leave the last entry with a trailing comma; strict JSON
        # readers other than VSCode's would choke on it.
        patched = re.sub(r",(\s*)\}(\s*)$", r"\1}\2", patched)
        scan_top_level(patched)  # guard: never hand back something unreadable

    return patched, changed
