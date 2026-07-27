#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Release pow-cli at the version currently committed.

Builds the distributions, creates an annotated tag, and pushes it. Pushing the
tag is what triggers .github/workflows/publish.yml, which publishes to TestPyPI
and then to PyPI after approval.

Run bump.py first and commit the result yourself; this script never edits a
pyproject.toml and never commits.

    uv run release.py
    uv run release.py --dry-run
    uv run release.py --no-push
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PKG_TOML = Path("packages/pow-cli/pyproject.toml")
ROOT_TOML = Path("pyproject.toml")
CHANGELOG = Path("packages/pow-cli/CHANGELOG.md")

# Must match the guard in .github/workflows/publish.yml, or the tag builds nothing.
CANONICAL_VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")

REPO_URL = "https://github.com/isaac-powerpack/pow"


def child_env() -> dict[str, str]:
    """Environment for nested commands.

    This script runs inside uv's own PEP 723 environment; leaking VIRTUAL_ENV
    into nested `uv` calls makes every one of them warn about a mismatch with
    the project's .venv.
    """
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    return env


def say(message: str = "") -> None:
    """Print, flushing so our output stays interleaved with the subprocesses'."""
    print(message, flush=True)


def die(message: str) -> None:
    sys.exit(f"error: {message}")


def run(*args: str, capture: bool = False) -> str:
    """Run a command, failing the release if it does."""
    result = subprocess.run(args, text=True, capture_output=capture, env=child_env())
    if result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        die(f"`{' '.join(args)}` failed")
    return result.stdout.strip() if capture else ""


def quiet(*args: str) -> int:
    """Run a command for its exit status only."""
    return subprocess.run(args, capture_output=True, env=child_env()).returncode


def git(*args: str, capture: bool = False) -> str:
    return run("git", *args, capture=capture)


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:  # non-interactive; treat silence as "no"
        return False


def project_version(path: Path) -> str:
    with path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="uv run release.py",
        description=(
            "Build, tag, and push the pow-cli version already committed in "
            "packages/pow-cli/pyproject.toml."
        ),
        epilog="Run bump.py first and commit its changes; this script never commits.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen; change nothing",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="skip the confirmation prompt",
    )
    parser.add_argument(
        "--no-push",
        dest="push",
        action="store_false",
        help="build and tag locally, but do not push (nothing is published)",
    )
    return parser.parse_args()


def preflight(args: argparse.Namespace) -> tuple[str, str, str]:
    """Run every check that can fail before anything is built or tagged."""
    if shutil.which("uv") is None:
        die("uv is not installed")

    # A dirty tree means the version bump is not committed yet, so the tag would
    # point at the wrong tree.
    if git("status", "--porcelain", capture=True):
        die(
            "working tree is not clean; commit the version bump first "
            "(run bump.py, then commit)"
        )

    version = project_version(PKG_TOML)
    tag = f"v{version}"

    if not CANONICAL_VERSION.fullmatch(version):
        die(
            f"{PKG_TOML} is '{version}', not a canonical PEP 440 release version; "
            f"the publish workflow would reject {tag}"
        )

    if quiet("git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}") == 0:
        die(f"tag {tag} already exists locally; bump the version first")

    if quiet("git", "ls-remote", "--exit-code", "--tags", "origin", tag) == 0:
        die(f"tag {tag} already exists on origin; bump the version first")

    branch = git("rev-parse", "--abbrev-ref", "HEAD", capture=True)
    if branch != "main" and not confirm(
        f"On branch '{branch}', not main. Release from here?", args.yes
    ):
        die("aborted")

    say(f"releasing pow-cli {version}  (tag {tag})")

    # The CI guard treats the root as a warning too -- it is a virtual project and
    # is never published.
    root_version = project_version(ROOT_TOML)
    if root_version != version:
        say(f"warning: {ROOT_TOML} is {root_version}, expected {version}")

    if f"[{version}]" not in CHANGELOG.read_text():
        say(f"warning: no '[{version}]' heading in {CHANGELOG}")

    return version, tag, branch


def main() -> None:
    args = parse_args()

    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        env=child_env(),
    )
    if root.returncode != 0:
        die("not inside a git repository")
    os.chdir(root.stdout.strip())

    version, tag, branch = preflight(args)

    if args.dry_run:
        say("\ndry run; would then:")
        say("  uv build --package pow-cli --out-dir dist")
        say(f"  git tag -a {tag} -m 'pow-cli {version}'")
        if args.push:
            say(f"  git push origin {branch} && git push origin {tag}")
        return

    if not confirm(f"Release {tag}?", args.yes):
        die("aborted")

    shutil.rmtree("dist", ignore_errors=True)
    run("uv", "build", "--package", "pow-cli", "--out-dir", "dist")

    git("tag", "-a", tag, "-m", f"pow-cli {version}")
    say(f"tagged {tag}")

    if not args.push:
        say(
            f"\nNot pushed. To release:\n"
            f"  git push origin {branch} && git push origin {tag}\n"
            f"To undo:\n"
            f"  git tag -d {tag}"
        )
        return

    try:
        git("push", "origin", branch)
        git("push", "origin", tag)
    except BaseException:
        say(f"\npush failed; the local tag is still there. To drop it:\n  git tag -d {tag}")
        raise

    say(
        f"\nPushed {tag}. The publish workflow builds and uploads to TestPyPI, then\n"
        f"waits for your approval on the 'pypi' environment:\n"
        f"  {REPO_URL}/actions"
    )


if __name__ == "__main__":
    main()
