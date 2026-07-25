import os

import pytest

from pow_cli.common.prompt import _path_completion, ask_path, complete_path


@pytest.fixture
def tree(tmp_path):
    """A small filesystem tree to complete against."""
    (tmp_path / "IsaacSim-ros_workspaces").mkdir()
    (tmp_path / "Isaac-other").mkdir()
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Isaac-notes.txt").write_text("")
    (tmp_path / ".hidden").mkdir()
    return tmp_path


# ── complete_path ───────────────────────────────────────────────────────────────

def test_completes_matching_prefix_only(tree):
    matches = complete_path(f"{tree}/Isaac")

    assert set(matches) == {
        f"{tree}/IsaacSim-ros_workspaces{os.sep}",
        f"{tree}/Isaac-other{os.sep}",
        f"{tree}/Isaac-notes.txt",
    }


def test_directories_get_trailing_separator(tree):
    matches = complete_path(f"{tree}/Projects")

    assert matches == [f"{tree}/Projects{os.sep}"]


def test_dirs_only_drops_files(tree):
    matches = complete_path(f"{tree}/Isaac", dirs_only=True)

    assert all(m.endswith(os.sep) for m in matches)
    assert not any("notes" in m for m in matches)


def test_hidden_entries_need_an_explicit_dot(tree):
    assert not any(".hidden" in m for m in complete_path(f"{tree}/"))
    assert complete_path(f"{tree}/.hid") == [f"{tree}/.hidden{os.sep}"]


def test_empty_prefix_lists_the_directory(tree):
    matches = complete_path(f"{tree}/")

    assert len(matches) == 4  # everything except .hidden
    assert matches == sorted(matches)


def test_no_match_returns_empty(tree):
    assert complete_path(f"{tree}/nope") == []


def test_tilde_is_preserved_in_matches(tree, monkeypatch):
    monkeypatch.setenv("HOME", str(tree))

    matches = complete_path("~/IsaacSim")

    assert matches == [f"~/IsaacSim-ros_workspaces{os.sep}"]


def test_tilde_completion_is_dirs_only_aware(tree, monkeypatch):
    monkeypatch.setenv("HOME", str(tree))

    assert complete_path("~/Isaac", dirs_only=True) == [
        f"~/Isaac-other{os.sep}",
        f"~/IsaacSim-ros_workspaces{os.sep}",
    ]


# ── the installed readline completer ────────────────────────────────────────────

@pytest.fixture
def completer(tree):
    """The (text, state) callable readline sees, for a dirs-only prompt."""
    readline = pytest.importorskip("readline")
    with _path_completion(dirs_only=True) as active:
        if not active:
            pytest.skip("readline unavailable")
        yield readline.get_completer()


def _all_states(completer, text):
    out = []
    state = 0
    while (match := completer(text, state)) is not None:
        out.append(match)
        state += 1
    return out


def test_completer_duplicates_a_unique_directory(completer, tree):
    """A duplicate stops readline appending a space, so typing can continue."""
    result = _all_states(completer, f"{tree}/Projec")

    assert result == [f"{tree}/Projects{os.sep}"] * 2


def test_completer_completes_into_a_directory(completer, tree):
    """Completing "dir/" offers its children, so a match never equals the input."""
    (tree / "Projects" / "sub").mkdir()

    assert _all_states(completer, f"{tree}/Projects{os.sep}") == [
        f"{tree}/Projects/sub{os.sep}"
    ] * 2


def test_completer_does_not_duplicate_a_unique_file(tree):
    """A file keeps readline's trailing space, which is the shell behaviour."""
    readline = pytest.importorskip("readline")
    with _path_completion(dirs_only=False) as active:
        if not active:
            pytest.skip("readline unavailable")
        assert _all_states(readline.get_completer(), f"{tree}/Isaac-not") == [
            f"{tree}/Isaac-notes.txt"
        ]


def test_completer_returns_every_ambiguous_match(completer, tree):
    result = _all_states(completer, f"{tree}/Isaac")

    assert result == [f"{tree}/Isaac-other{os.sep}", f"{tree}/IsaacSim-ros_workspaces{os.sep}"]


def test_completer_absorbs_a_trailing_space(completer, tree):
    """A space readline appended earlier must not break the next completion."""
    assert _all_states(completer, f"{tree}/Projec ") == [f"{tree}/Projects{os.sep}"] * 2


def test_completer_returns_nothing_when_no_match(completer, tree):
    assert _all_states(completer, f"{tree}/nope") == []


def test_completer_uses_line_wide_delimiters(tree):
    """Default delims split on "/" and "~", which would break path completion."""
    readline = pytest.importorskip("readline")
    with _path_completion() as active:
        if not active:
            pytest.skip("readline unavailable")
        assert readline.get_completer_delims() == "\n"


# ── ask_path ────────────────────────────────────────────────────────────────────

def test_ask_path_strips_whitespace_and_trailing_separator(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "  ~/ws/  ")

    assert ask_path("Path", default="~/default") == "~/ws"


def test_ask_path_keeps_root_separator(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "/")

    assert ask_path("Path", default="~/default") == "/"


def test_ask_path_empty_input_uses_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    assert ask_path("Path", default="~/IsaacSim-ros_workspaces") == "~/IsaacSim-ros_workspaces"


def test_ask_path_restores_readline_state(monkeypatch):
    readline = pytest.importorskip("readline")

    def sentinel_completer(text, state):  # pragma: no cover - never called
        return None

    readline.set_completer(sentinel_completer)
    readline.set_completer_delims(" \t\n")
    monkeypatch.setattr("builtins.input", lambda prompt="": "~/ws")

    ask_path("Path", default="~/default")

    assert readline.get_completer() is sentinel_completer
    assert readline.get_completer_delims() == " \t\n"


def test_ask_path_prompt_is_passed_to_input(monkeypatch):
    """readline needs the prompt to redraw the line, so input() must receive it."""
    seen = {}

    def fake_input(prompt=""):
        seen["prompt"] = prompt
        return "~/ws"

    monkeypatch.setattr("builtins.input", fake_input)

    ask_path("Path to clone", default="~/IsaacSim-ros_workspaces")

    assert "Path to clone" in seen["prompt"]
    assert "~/IsaacSim-ros_workspaces" in seen["prompt"]
