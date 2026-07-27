#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bump the pow-cli version.

Updates packages/pow-cli/pyproject.toml, the workspace root pyproject.toml (kept
in lockstep), and uv.lock. Touches nothing else -- no commit, no tag, no push.
Review the diff, write the CHANGELOG entry, and commit yourself, then run
release.py to build and tag.

    uv run bump.py --bump patch
    uv run bump.py --bump minor --bump rc
    uv run bump.py 0.3.0rc1
    uv run bump.py --bump minor --dry-run
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
VERSIONED_FILES = [str(ROOT_TOML), str(PKG_TOML), "uv.lock"]

BUMP_CHOICES = ["major", "minor", "patch", "stable", "alpha", "beta", "rc"]

# Must match the guard in .github/workflows/publish.yml, or the tag builds nothing.
CANONICAL_VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")


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
    """Run a command, failing the bump if it does."""
    result = subprocess.run(args, text=True, capture_output=capture, env=child_env())
    if result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        die(f"`{' '.join(args)}` failed")
    return result.stdout.strip() if capture else ""


def project_version(path: Path) -> str:
    with path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="uv run bump.py",
        description="Bump the pow-cli version in both pyproject.toml files and uv.lock.",
        epilog=(
            "The resulting version must be canonical PEP 440 -- X.Y.Z optionally "
            "followed by aN, bN, or rcN. .post and .dev releases are rejected "
            "because the publish workflow refuses to build them. Nothing is "
            "committed; that is yours to do."
        ),
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="set an exact version, e.g. 0.3.0rc1",
    )
    parser.add_argument(
        "--bump",
        action="append",
        choices=BUMP_CHOICES,
        metavar="PART",
        help=(
            "bump a version component (%(choices)s); repeatable, "
            "e.g. --bump minor --bump rc"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change; change nothing",
    )

    args = parser.parse_args()
    if args.version and args.bump:
        parser.error("give either an exact version or --bump, not both")
    if not args.version and not args.bump:
        parser.error("give a version (e.g. 0.3.0rc1) or --bump PART")
    return args


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

    if shutil.which("uv") is None:
        die("uv is not installed")

    spec = [args.version] if args.version else [
        arg for part in args.bump for arg in ("--bump", part)
    ]

    # Resolve the target version before writing anything.
    current = run("uv", "version", "--package", "pow-cli", "--short", capture=True)
    new_version = run(
        "uv", "version", "--package", "pow-cli", "--dry-run", "--short", *spec,
        capture=True,
    )

    if not CANONICAL_VERSION.fullmatch(new_version):
        die(
            f"'{new_version}' is not a canonical PEP 440 release version; "
            f"the publish workflow would reject v{new_version}"
        )

    say(f"pow-cli {current} => {new_version}")

    if args.dry_run:
        say("\ndry run; would then:")
        say(f"  uv version --package pow-cli --no-sync {' '.join(spec)}")
        say(f"  uv version --no-sync {new_version}        # workspace root")
        return

    # --no-sync relocks uv.lock (which pins pow-cli's own version) without
    # rebuilding the virtualenv, so this never reaches the NVIDIA index.
    run("uv", "version", "--package", "pow-cli", "--no-sync", *spec)
    run("uv", "version", "--no-sync", new_version)

    for toml in (PKG_TOML, ROOT_TOML):
        got = project_version(toml)
        if got != new_version:
            die(f"{toml} is {got}, expected {new_version}")

    say("\nchanged:")
    for path in VERSIONED_FILES:
        say(f"  {path}")

    if f"[{new_version}]" not in CHANGELOG.read_text():
        say(f"\nwarning: no '[{new_version}]' heading in {CHANGELOG}")

    say(
        f"\nNothing committed. Next:\n"
        f"  1. add the {new_version} entry to {CHANGELOG}\n"
        f"  2. git commit -m 'chore: bump version to v{new_version}'\n"
        f"  3. uv run release.py\n"
        f"To undo:\n"
        f"  git checkout -- {' '.join(VERSIONED_FILES)}"
    )


if __name__ == "__main__":
    main()
