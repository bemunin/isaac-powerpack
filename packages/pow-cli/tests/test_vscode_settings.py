import json

import pytest

from pow_cli.common import jsonc
from pow_cli.core import vscode_settings


class TestJsoncScanner:
    """The scanner must cope with what VSCode and Isaac Sim actually write."""

    def test_scans_entries_with_comments_and_trailing_comma(self):
        text = """\
{
    // a leading comment
    "a": [1, 2],
    /* block */ "b": {"nested": {"deep": true}},
    "c": "text with } and , inside",
    "d": false,
}
"""
        entries, close = jsonc.scan_top_level(text)

        assert [e.key for e in entries] == ["a", "b", "c", "d"]
        assert text[close] == "}"
        values = [jsonc.parse_value(text[e.value_start:e.value_end]) for e in entries]
        assert values == [[1, 2], {"nested": {"deep": True}}, "text with } and , inside", False]

    def test_reports_duplicate_keys_in_order(self):
        entries, _ = jsonc.scan_top_level('{"a": 1, "a": 2}')
        assert [e.key for e in entries] == ["a", "a"]

    def test_strip_jsonc_drops_comments_and_trailing_commas(self):
        text = '{\n // note\n "a": [1, 2,],\n "b": "// not a comment",\n}'
        assert json.loads(jsonc.strip_jsonc(text)) == {"a": [1, 2], "b": "// not a comment"}

    @pytest.mark.parametrize("bad", ['["not", "an", "object"]', '{"a": 1', '{"a"}', '{"a": }'])
    def test_rejects_documents_it_cannot_patch(self, bad):
        with pytest.raises(jsonc.JsoncError):
            jsonc.scan_top_level(bad)

    def test_long_lists_are_rendered_one_entry_per_line(self):
        assert jsonc.render_value([120], 4) == "[120]"
        rendered = jsonc.render_value([f"a-very-long-path-number-{i}" for i in range(5)], 4)
        assert rendered.startswith("[\n        ")
        assert rendered.endswith("\n    ]")


class TestJsoncPatch:
    def test_replaces_values_and_keeps_everything_else(self):
        text = '{\n    // mine\n    "a": 1,\n    "keep": "me"\n}\n'

        patched, changed = jsonc.patch(text, {"a": 2})

        assert changed == {"a": (1, 2)}
        assert patched == '{\n    // mine\n    "a": 2,\n    "keep": "me"\n}\n'

    def test_appends_missing_keys_before_the_closing_brace(self):
        patched, changed = jsonc.patch('{\n    "keep": "me"\n}\n', {"new": "value"})

        assert changed == {"new": (None, "value")}
        assert patched == '{\n    "keep": "me",\n    "new": "value"\n}\n'
        assert json.loads(jsonc.strip_jsonc(patched)) == {"keep": "me", "new": "value"}

    def test_appends_into_an_empty_object(self):
        patched, _ = jsonc.patch("{}", {"a": 1})
        assert json.loads(patched) == {"a": 1}

    def test_keeps_the_first_of_a_duplicated_managed_key(self):
        text = '{\n    "a": 1,\n    "b": 2,\n    "a": 9\n}\n'

        patched, changed = jsonc.patch(text, {"a": 1})

        assert changed == {}          # the value never moved...
        assert patched != text        # ...but the duplicate is gone
        assert [e.key for e in jsonc.scan_top_level(patched)[0]] == ["a", "b"]

    def test_removes_deprecated_keys(self):
        text = '{\n    "old": "on",\n    "keep": 1\n}\n'

        patched, changed = jsonc.patch(text, {}, remove=("old",))

        assert changed == {"old": ("on", None)}
        assert json.loads(jsonc.strip_jsonc(patched)) == {"keep": 1}

    def test_removing_the_last_entry_leaves_valid_json(self):
        patched, _ = jsonc.patch('{\n    "keep": 1,\n    "old": 2\n}\n', {}, remove=("old",))
        assert json.loads(patched) == {"keep": 1}

    def test_returns_the_original_text_when_nothing_changes(self):
        text = '{\n    "a": 1\n}\n'
        patched, changed = jsonc.patch(text, {"a": 1})
        assert (patched, changed) == (text, {})

    def test_uses_the_indent_the_file_already_uses(self):
        patched, _ = jsonc.patch('{\n  "a": 1\n}\n', {"b": 2})
        assert patched == '{\n  "a": 1,\n  "b": 2\n}\n'


ISAACSIM_SETTINGS = """\
{
    "editor.rulers": [120],
    "typescript.tsc.autoDetect": "off",

    // Those paths are automatically filled by build system:
    "python.analysis.extraPaths": [
        "exts/isaacsim.core.api",
        "kit/python/lib/python3.12",
],

    "python.languageServer": "Pylance",
    "python.defaultInterpreterPath": "${workspaceFolder}/kit/python/bin/python3",
    "python.jediEnabled": false,
    "python.languageServer": "Pylance",
    "ROS2.distro": "humble"
}
"""


@pytest.fixture
def isaacsim_settings(tmp_path):
    """A stand-in for `_isaacsim/.vscode/settings.json`, JSONC quirks included."""
    src = tmp_path / "_isaacsim" / ".vscode" / "settings.json"
    src.parent.mkdir(parents=True)
    src.write_text(ISAACSIM_SETTINGS)
    return src


@pytest.fixture
def dest(tmp_path):
    return tmp_path / ".vscode" / "settings.json"


class TestExtraPaths:
    def test_paths_are_repointed_at_the_symlink(self, isaacsim_settings):
        assert vscode_settings.extra_paths(isaacsim_settings) == [
            "_isaacsim/exts/isaacsim.core.api",
            "_isaacsim/kit/python/lib/python3.12",
        ]

    def test_already_prefixed_paths_are_left_alone(self, tmp_path):
        src = tmp_path / "settings.json"
        src.write_text('{"python.analysis.extraPaths": ["_isaacsim/exts/a"]}')
        assert vscode_settings.extra_paths(src) == ["_isaacsim/exts/a"]

    @pytest.mark.parametrize("content", [None, "{ not json", '{"other": 1}'])
    def test_unusable_sources_yield_none(self, tmp_path, content):
        src = tmp_path / "settings.json"
        if content is not None:
            src.write_text(content)
        assert vscode_settings.extra_paths(src) is None


class TestApply:
    """`pow init` must own its keys without touching anything else."""

    def test_creates_the_managed_block_when_there_is_no_file(self, dest, isaacsim_settings):
        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Created"
        assert result["warning"] is None
        settings = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert settings["editor.rulers"] == [120]
        assert settings["js/ts.tsc.autoDetect"] == "off"
        assert settings["python.defaultInterpreterPath"] == "_isaacsim/kit/python/bin/python3"
        assert settings["python.linting.flake8Enabled"] is True
        assert settings["ROS2.distro"] == "humble"
        assert settings["python.analysis.extraPaths"] == [
            "_isaacsim/exts/isaacsim.core.api",
            "_isaacsim/kit/python/lib/python3.12",
        ]
        # The explanatory comments are written too, and the file stays readable.
        assert "// Use flake8 for linting" in dest.read_text()

    def test_creation_skips_extra_paths_when_the_source_is_unusable(self, dest, tmp_path):
        result = vscode_settings.apply(dest, tmp_path / "missing.json")

        assert result["status"] == "Created"
        assert vscode_settings.EXTRA_PATHS_KEY in result["warning"]
        written = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert vscode_settings.EXTRA_PATHS_KEY not in written

    def test_merge_keeps_the_users_own_settings_and_comments(self, dest, isaacsim_settings):
        dest.parent.mkdir(parents=True)
        dest.write_text(
            '{\n'
            '    // my own preference\n'
            '    "editor.rulers": [100],\n'
            '    "files.autoSave": "afterDelay",\n'
            '    "python.analysis.typeCheckingMode": "basic"\n'
            '}\n'
        )

        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Updated"
        content = dest.read_text()
        assert "// my own preference" in content
        settings = json.loads(jsonc.strip_jsonc(content))
        assert settings["files.autoSave"] == "afterDelay"
        assert settings["python.analysis.typeCheckingMode"] == "basic"
        # A managed key the user had set differently is pow's to decide.
        assert settings["editor.rulers"] == [120]
        assert result["changed"]["editor.rulers"] == ([100], [120])

    def test_cleans_up_what_older_pow_versions_wrote(self, dest, isaacsim_settings):
        """A file copied by the pre-merge init has duplicates and a renamed key."""
        dest.parent.mkdir(parents=True)
        dest.write_text(
            '{\n'
            '    "typescript.tsc.autoDetect": "off",\n'
            '    "python.jediEnabled": false,\n'
            '    "python.languageServer": "Pylance",\n'
            '    "python.jediEnabled": false\n'
            '}\n'
        )

        vscode_settings.apply(dest, isaacsim_settings)

        keys = [e.key for e in jsonc.scan_top_level(dest.read_text())[0]]
        assert keys.count("python.jediEnabled") == 1
        assert "typescript.tsc.autoDetect" not in keys
        assert "js/ts.tsc.autoDetect" in keys

    def test_second_run_is_a_no_op(self, dest, isaacsim_settings):
        vscode_settings.apply(dest, isaacsim_settings)
        before = dest.read_text()

        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Already up to date"
        assert result["changed"] == {}
        assert dest.read_text() == before

    def test_extra_paths_follow_the_linked_version(self, dest, tmp_path, isaacsim_settings):
        vscode_settings.apply(dest, isaacsim_settings)
        first = json.loads(jsonc.strip_jsonc(dest.read_text()))["python.analysis.extraPaths"]

        other = tmp_path / "other.json"
        other.write_text('{"python.analysis.extraPaths": ["exts/isaacsim.hsb.core"]}')
        result = vscode_settings.apply(dest, other)

        assert result["status"] == "Updated"
        second = json.loads(jsonc.strip_jsonc(dest.read_text()))["python.analysis.extraPaths"]
        assert first != second
        assert second == ["_isaacsim/exts/isaacsim.hsb.core"]

    def test_creates_the_performance_block(self, dest, isaacsim_settings):
        """The excludes that keep the editor off the Isaac Sim symlink."""
        vscode_settings.apply(dest, isaacsim_settings)

        content = dest.read_text()
        settings = json.loads(jsonc.strip_jsonc(content))
        assert settings["files.watcherExclude"]["**/_isaacsim/**"] is True
        assert settings["search.exclude"]["**/_isaacsim"] is True
        assert settings["search.followSymlinks"] is False
        assert settings["files.exclude"]["**/*.pyc"] is True
        assert "_isaacsim/**" in settings["python.analysis.exclude"]
        assert settings["taskexplorer.useVscWatcherExclude"] is True
        assert "**/_isaacsim/**" in settings["taskexplorer.exclude"]
        assert settings["taskexplorer.enablePersistentFileCaching"] is True
        # The block is explained, and comes before the Isaac Sim settings.
        assert "// Performance:" in content
        assert content.index('"files.watcherExclude"') < content.index('"editor.rulers"')

    def test_container_settings_gain_pows_entries_and_keep_the_projects(
        self, dest, isaacsim_settings
    ):
        dest.parent.mkdir(parents=True)
        dest.write_text(
            '{\n'
            '    "files.watcherExclude": {"**/my_data/**": true},\n'
            '    "python.analysis.exclude": ["my_vendored/**"]\n'
            '}\n'
        )

        vscode_settings.apply(dest, isaacsim_settings)

        settings = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert settings["files.watcherExclude"]["**/my_data/**"] is True
        assert settings["files.watcherExclude"]["**/_isaacsim/**"] is True
        assert settings["python.analysis.exclude"][0] == "my_vendored/**"
        assert "_isaacsim/**" in settings["python.analysis.exclude"]

    def test_a_projects_own_exclude_value_is_never_flipped(self, dest, isaacsim_settings):
        """Union means union: an entry the project set stays as the project set it."""
        dest.parent.mkdir(parents=True)
        dest.write_text('{\n    "search.exclude": {"**/_isaacsim": false}\n}\n')

        vscode_settings.apply(dest, isaacsim_settings)

        settings = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert settings["search.exclude"]["**/_isaacsim"] is False
        assert settings["search.exclude"]["**/__pycache__"] is True

    def test_the_interpreter_is_seeded_but_never_overridden(self, dest, isaacsim_settings):
        vscode_settings.apply(dest, isaacsim_settings)
        seeded = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert seeded["python.defaultInterpreterPath"] == "_isaacsim/kit/python/bin/python3"

        dest.write_text(
            dest.read_text().replace(
                '"_isaacsim/kit/python/bin/python3"', '"${workspaceFolder}/.venv/bin/python"'
            )
        )
        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Already up to date"
        kept = json.loads(jsonc.strip_jsonc(dest.read_text()))
        assert kept["python.defaultInterpreterPath"] == "${workspaceFolder}/.venv/bin/python"

    def test_unioned_blocks_are_stable_across_runs(self, dest, isaacsim_settings):
        """The union must not re-append or reorder what it already merged."""
        dest.parent.mkdir(parents=True)
        dest.write_text('{\n    "taskexplorer.exclude": ["**/my_data/**"]\n}\n')

        vscode_settings.apply(dest, isaacsim_settings)
        before = dest.read_text()
        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Already up to date"
        assert dest.read_text() == before

    def test_an_unparseable_file_is_reported_and_never_rewritten(self, dest, isaacsim_settings):
        dest.parent.mkdir(parents=True)
        broken = '{\n    "editor.rulers": [120\n'
        dest.write_text(broken)

        result = vscode_settings.apply(dest, isaacsim_settings)

        assert result["status"] == "Error"
        assert result["message"]
        assert dest.read_text() == broken
