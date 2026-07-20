"""Lint command implementation — pow lint dry-run / fix."""

from pathlib import Path

import click
from rich.markup import escape
from rich.panel import Panel

from ..common.utils import console
from ..core.linter import AliasConfig, lint_file, fix_file, scan_directory


# ── CLI group ─────────────────────────────────────────────────────────────────


class _LintGroup(click.Group):
    """Custom group that defaults to 'dry-run' when no subcommand is given."""

    def parse_args(self, ctx, args):
        # Let --help pass through to show group-level help
        if "--help" in args or "-h" in args:
            return super().parse_args(ctx, args)
        # If first arg is not a known subcommand, prepend 'dry-run'
        if args and args[0] not in self.commands:
            args = ["dry-run"] + args
        elif not args:
            args = ["dry-run"]
        return super().parse_args(ctx, args)


@click.group(name="lint", cls=_LintGroup)
def lint_group():
    """Check .usda files for compatibility issues.

    Defaults to 'dry-run' when no subcommand is given.
    """
    pass


# ── pow lint dry-run ──────────────────────────────────────────────────────────


@lint_group.command(name="dry-run")
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "-s", "--short",
    is_flag=True,
    default=False,
    help="Show only file path and line number.",
)
def dry_run_cmd(path, short):
    """Report lint issues without modifying any files.

    \b
    PATH  File or directory to scan (default: current directory).
    """
    target = Path(path)
    alias_config = _load_alias_config()
    files = scan_directory(target)

    if not files:
        console.print(
            Panel(
                "[dim]No .usda files found.[/dim]",
                title="[dim]Lint[/dim]",
                border_style="dim",
            )
        )
        return

    total_issues = 0
    files_with_issues = 0

    for usda_file in files:
        issues = lint_file(usda_file, alias_config)
        if not issues:
            continue

        files_with_issues += 1
        total_issues += len(issues)

        for issue in issues:
            _print_issue(issue, short=short)

    console.print()
    if total_issues == 0:
        console.print(
            Panel(
                f"[green]✔[/green]  No issues found in "
                f"[bold]{len(files)}[/bold] file(s).",
                title="[bold green]Lint passed[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]✘[/bold red]  Found [bold]{total_issues}[/bold] "
                f"issue(s) in [bold]{files_with_issues}[/bold] file(s).\n"
                f"[dim]Run [bold]pow lint fix[/bold] to apply fixes.[/dim]",
                title="[bold red]Lint failed[/bold red]",
                border_style="red",
            )
        )
        raise SystemExit(1)


# ── pow lint fix ──────────────────────────────────────────────────────────────


@lint_group.command(name="fix")
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "-s", "--short",
    is_flag=True,
    default=False,
    help="Show only file path and line number.",
)
def fix_cmd(path, short):
    """Fix lint issues in .usda files.

    \b
    PATH  File or directory to scan (default: current directory).
    """
    target = Path(path)
    alias_config = _load_alias_config()
    files = scan_directory(target)

    if not files:
        console.print(
            Panel(
                "[dim]No .usda files found.[/dim]",
                title="[dim]Lint[/dim]",
                border_style="dim",
            )
        )
        return

    total_fixed = 0
    files_fixed = 0

    for usda_file in files:
        issues = lint_file(usda_file, alias_config)
        if not issues:
            continue

        fix_file(usda_file, issues)
        files_fixed += 1
        total_fixed += len(issues)

        for issue in issues:
            _print_fix(issue, short=short)

    console.print()
    if total_fixed == 0:
        console.print(
            Panel(
                f"[green]✔[/green]  No issues found in "
                f"[bold]{len(files)}[/bold] file(s).",
                title="[bold green]Lint passed[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[green]✔[/green]  Fixed [bold]{total_fixed}[/bold] "
                f"issue(s) in [bold]{files_fixed}[/bold] file(s).",
                title="[bold green]Lint fixed[/bold green]",
                border_style="green",
            )
        )


# ── Private helpers ───────────────────────────────────────────────────────────


def _load_alias_config() -> AliasConfig:
    """Load alias config, printing a warning if omniverse.toml is missing."""
    config = AliasConfig()
    if not config.has_pow_assets:
        console.print(
            "[yellow]⚠[/yellow]  [dim]pow-assets alias not found in "
            "omniverse.toml — lint will still detect relative paths.[/dim]"
        )
    return config


def _print_issue(issue, *, short: bool = False) -> None:
    """Print a single lint issue."""
    rel_path = _short_path(issue.file)
    if short:
        if "simready_content" in issue.original:
            problem = "relative path → use sim-ready staging S3 URL"
        elif "Pow" in issue.original:
            problem = "relative path → use pow-assets alias"
        else:
            problem = "relative path → use NVIDIA production S3 URL"
        console.print(
            f"  [dim]{rel_path}[/dim]:[green]{issue.line}[/green]"
            f"  [red]●[/red] {problem}",
            soft_wrap=True,
        )
    else:
        console.print(
            f"  [dim]{rel_path}[/dim]:[green]{issue.line}[/green]",
            soft_wrap=True,
        )
        console.print(
            f"    [red]●[/red] [dim]{escape(issue.original)}[/dim]",
            soft_wrap=True,
        )
        console.print(
            f"    [green]→[/green] [dim]{escape(issue.replacement)}[/dim]",
            soft_wrap=True,
        )
        console.print()


def _print_fix(issue, *, short: bool = False) -> None:
    """Print a single applied fix."""
    rel_path = _short_path(issue.file)
    if short:
        console.print(
            f"  [dim]{rel_path}[/dim]:[green]{issue.line}[/green]"
            f"  [green]✔[/green] fixed relative path",
            soft_wrap=True,
        )
    else:
        console.print(
            f"  [dim]{rel_path}[/dim]:[green]{issue.line}[/green]",
            soft_wrap=True,
        )
        console.print(
            f"    [green]✔[/green] [dim]{escape(issue.original)}[/dim]",
            soft_wrap=True,
        )
        console.print(
            f"    [green]→[/green] [dim]{escape(issue.replacement)}[/dim]",
            soft_wrap=True,
        )
        console.print()


def _short_path(p: Path) -> str:
    """Try to make the path relative to cwd for cleaner output."""
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)

