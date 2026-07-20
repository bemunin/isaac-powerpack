import click
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from ..common.utils import console, get_terminal_width
from ..core.asset_manager import AssetManager, AssetError


# ── Shared UI helpers ─────────────────────────────────────────────────────────

_SUPPORTED_ALIAS_APPS = {"isaacsim", "simready", "none"}


def _error_panel(message: str, title: str = "Asset Error") -> Panel:
    """Build a red-bordered error panel."""
    return Panel(
        f"[bold red]✘[/bold red]  {message}",
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
        width=get_terminal_width(),
    )

def _handle_error(error: Exception) -> None:
    """Print an error panel and exit."""
    if isinstance(error, AssetError):
        console.print(_error_panel(str(error)))
    else:
        console.print(f"[bold red]✘ Unexpected error:[/bold red] {error}")
    raise SystemExit(1)


# ── CLI group ─────────────────────────────────────────────────────────────────


@click.group(name="asset")
def asset_group():
    """Manage Isaac Sim assets."""
    pass


# ── pow asset set ─────────────────────────────────────────────────────────────


@asset_group.command(name="set")
@click.argument("assets_path")
@click.option(
    "-a",
    "--alias-support",
    "alias_support",
    multiple=True,
    metavar="APP",
    help=(
        "Apply alias/patch support for the specified app (repeatable). "
        "Supported: isaacsim, simready, none. "
        "Defaults to all (isaacsim + simready) when omitted."
    ),
)
def set_cmd(assets_path: str, alias_support: tuple[str, ...]):
    """Set the local asset path for pow.

    \b
    ASSETS_PATH  Absolute or relative path to the local assets directory.

    \b
    What this command does:
      1. Validates the given path exists.
      2. Creates a symlink at ~/.pow/assets → ASSETS_PATH.
      3. Writes the [asset] config in ~/.pow/system.toml.
      4. Registers a 'pow-assets' alias in omniverse.toml.
      5. Applies alias support (default: all):
           isaacsim  — patches isaacsim.exp.base.kit + 4 production S3 aliases.
           simready — adds 2 staging S3 aliases to omniverse.toml.
           none      — skips all alias patching.
    """
    apps = _resolve_alias_apps(alias_support)

    manager = AssetManager()
    console.print()
    try:
        abs_path = manager.set_local_asset_path(assets_path)

        details = Table.grid(padding=(0, 2))
        details.add_column(style="dim")
        details.add_column()
        details.add_row("Assets path     :", f"[bold cyan]{abs_path}[/bold cyan]")
        details.add_row("Symlink         :", f"[dim]{manager.get_assets_symlink_path()}[/dim]")
        details.add_row("Assets alias    :", f"[dim]{manager.POW_ASSETS_ALIAS}[/dim]")

        if "isaacsim" in apps:
            _apply_isaacsim_aliases(manager, abs_path, details)

        if "simready" in apps:
            _apply_simready_aliases(manager, details)

        console.print(
            Panel(
                details,
                title="[bold green]✔  Local asset configured[/bold green]",
                border_style="green",
                width=get_terminal_width(),
            )
        )
    except (AssetError, Exception) as e:
        _handle_error(e)


def _resolve_alias_apps(alias_support: tuple[str, ...]) -> set[str]:
    """Parse and validate the -a / --alias-support flags."""
    raw = {a.lower() for a in alias_support}
    unknown = raw - _SUPPORTED_ALIAS_APPS
    if unknown:
        console.print(
            Panel(
                f"[bold red]✘[/bold red]  Unknown alias support target(s): {', '.join(sorted(unknown))}\n"
                f"Supported values: {', '.join(sorted(_SUPPORTED_ALIAS_APPS))}",
                title="[bold red]Asset Error[/bold red]",
                border_style="red",
                width=get_terminal_width(),
            )
        )
        raise SystemExit(1)

    if not raw:
        return {"isaacsim", "simready"}
    if "none" in raw:
        return set()
    return raw


def _apply_isaacsim_aliases(
    manager: AssetManager, abs_path: str, details: Table
) -> None:
    """Patch isaacsim.exp.base.kit and register production S3 aliases."""
    try:
        patched = manager.patch_isaacsim_kit()
        kit_status = (
            "[green]Patched[/green]"
            if patched
            else "[dim]Already patched — skipped[/dim]"
        )
    except AssetError as kit_err:
        kit_status = f"[yellow]Skipped:[/yellow] {escape(str(kit_err))}"
    details.add_row("isaacsim.exp.base.kit :", kit_status)

    try:
        manager.register_isaacsim_s3_aliases()
        s3_status = "[green]Registered (4 production S3 URLs → assets symlink)[/green]"
    except Exception as s3_err:
        s3_status = f"[red]Failed:[/red] {escape(str(s3_err))}"
    details.add_row("omniverse.toml (isaacsim):", s3_status)


def _apply_simready_aliases(manager: AssetManager, details: Table) -> None:
    """Register staging S3 aliases for SimReady assets."""
    try:
        manager.register_sim_ready_s3_aliases()
        sr_status = "[green]Registered (2 staging S3 URLs → assets symlink)[/green]"
    except Exception as sr_err:
        sr_status = f"[red]Failed:[/red] {escape(str(sr_err))}"
    details.add_row("omniverse.toml (simready):", sr_status)


# ── pow asset unset ───────────────────────────────────────────────────────────


@asset_group.command(name="unset")
def unset_cmd():
    """Remove the local asset path configuration.

    \b
    What this command does:
      1. Removes the ~/.pow/assets symlink.
      2. Clears [asset] config in ~/.pow/system.toml.
      3. Removes [alias] section from omniverse.toml.
      4. Removes the pow patch block from isaacsim.exp.base.kit (if present).

    Each step is performed independently — a failure in one step does not
    prevent the others from running.
    """
    manager = AssetManager()
    console.print()
    try:
        results = manager.unset_local_asset_path()
        _print_unset_results(results)
    except AssetError as e:
        console.print(
            Panel(
                Text.from_markup("[bold yellow]⚠[/bold yellow]  ") + Text(str(e)),
                title="[bold yellow]Nothing to unset[/bold yellow]",
                border_style="yellow",
                width=get_terminal_width(),
            )
        )
        raise SystemExit(1)
    except Exception as e:
        _handle_error(e)


def _print_unset_results(results: dict[str, str]) -> None:
    """Render the outcome grid for the unset command."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=34)
    grid.add_column()

    for label, outcome in results.items():
        safe_outcome = escape(outcome)
        if "skipped" in outcome.lower():
            icon = "[yellow]–[/yellow]"
            outcome_markup = f"[dim]{safe_outcome}[/dim]"
        elif "failed" in outcome.lower():
            icon = "[bold red]✘[/bold red]"
            outcome_markup = f"[red]{safe_outcome}[/red]"
        else:
            icon = "[bold green]✔[/bold green]"
            outcome_markup = safe_outcome
        grid.add_row(f"{icon}  [dim]{escape(label)}[/dim]", outcome_markup)

    console.print(
        Panel(
            grid,
            title="[bold green]Local asset disabled[/bold green]",
            border_style="green",
            width=get_terminal_width(),
        )
    )


# ── pow asset info ────────────────────────────────────────────────────────────


@asset_group.command(name="info")
def info_cmd():
    """Show details about the current local asset configuration."""
    manager = AssetManager()
    console.print()
    try:
        data = manager.get_asset_list_data()
        _print_asset_status_panel(data)
    except Exception as e:
        console.print(
            Text.from_markup("[bold red]✘ Failed to load asset data:[/bold red] ")
            + Text(str(e))
        )
        raise SystemExit(1)


def _print_asset_status_panel(data) -> None:
    """Render the asset status panel (used by `pow asset info`)."""
    if not data.local_path:
        console.print(
            Panel(
                "[dim]○  Local assets not configured  —  run [bold]pow asset set <path>[/bold] to configure[/dim]",
                title="[dim]Status[/dim]",
                border_style="dim",
                padding=(1, 2),
                width=get_terminal_width(),
            )
        )
        console.print()
        return

    manager = AssetManager()
    symlink_path = manager.get_assets_symlink_path()

    if data.symlink_ok:
        dot = "[bold green]●[/bold green]"
        status_text = "[bold green]Active[/bold green]"
    else:
        dot = "[bold red]●[/bold red]"
        status_text = "[bold red]Broken Link[/bold red]"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", style="dim")
    grid.add_column()

    grid.add_row("Status", f"{dot}  {status_text}")
    grid.add_row("Location", f"[bold cyan]{escape(data.local_path)}[/bold cyan]")

    symlink_status = (
        "[green]✔ valid[/green]" if data.symlink_ok else "[bold red]✘ broken[/bold red]"
    )
    grid.add_row(
        "Symlink",
        f"[dim]{escape(str(symlink_path))}[/dim]  ({symlink_status})",
    )

    console.print(
        Panel(
            grid,
            title="[bold blue]Local Asset Configuration[/bold blue]",
            border_style="blue" if data.symlink_ok else "red",
            padding=(1, 2),
            width=get_terminal_width(),
        )
    )
    console.print()


# ── pow asset list ────────────────────────────────────────────────────────────


@asset_group.command(name="list")
def list_cmd():
    """List supported assets mapping."""
    manager = AssetManager()
    console.print()
    try:
        from ..core.asset_manager import REGISTRIES

        target_groups = set()
        for r in REGISTRIES:
            if r["file"] == "isaacsim_assets_5_1_0.toml":
                target_groups.update(r["group_keys"])

        data = manager.get_asset_list_data()
        entries = [e for e in data.entries if e.group_name in target_groups]

        if not entries:
            console.print("[dim]No assets found.[/dim]")
            return

        sorted_entries = sorted(entries, key=lambda x: (x.group_name, x.name))

        table = Table(header_style="bold white")
        table.add_column("Group", style="bold blue")
        table.add_column("Name", style="cyan")
        table.add_column("Size", justify="right", style="green")

        current_group = None
        for entry in sorted_entries:
            display_group = ""
            if entry.group_name != current_group:
                display_group = escape(entry.group_name)
                current_group = entry.group_name
                
            table.add_row(display_group, escape(entry.name), escape(entry.size))

        console.print(table)
        console.print()

    except Exception as e:
        _handle_error(e)


# ── pow asset add ─────────────────────────────────────────────────────────────


@asset_group.command(name="add")
@click.argument("target")
@click.option("-n", "--name", "is_name", is_flag=True, help="Install asset by name.")
@click.option("-g", "--group", "is_group", is_flag=True, help="Install asset by group (default).")
@click.option("-k", "--keep", type=str, metavar="PATH", help="Keep downloaded files and move them to this location.")
def add_cmd(target: str, is_name: bool, is_group: bool, keep: str | None):
    """Install assets by name or group."""
    manager = AssetManager()
    console.print()
    try:
        # Default to group if neither is specified
        if not is_name and not is_group:
            is_group = True
            
        data = manager.get_asset_list_data()
        valid_groups = {e.group_name for e in data.entries}
        valid_names = {e.name for e in data.entries}
        term_width = get_terminal_width()

        if is_group:
            if target not in valid_groups:
                if target in valid_names:
                    console.print(
                        Panel(
                            f"[bold red]✘[/bold red]  Group '{target}' not found.\n\n"
                            f"[dim]Did you mean to install by name? Try using the [bold]-n[/bold] flag:[/dim]\n"
                            f"  pow asset add -n {target}",
                            title="[bold red]Asset Error[/bold red]",
                            border_style="red",
                            width=term_width
                        )
                    )
                else:
                    console.print(
                        Panel(
                            f"[bold red]✘[/bold red]  Group '{target}' not found in registry.",
                            title="[bold red]Asset Error[/bold red]",
                            border_style="red",
                            width=term_width
                        )
                    )
                raise SystemExit(1)
                
            manager.install_assets(target, is_group=True, keep_path=keep)

        elif is_name:
            if target not in valid_names:
                console.print(
                    Panel(
                        f"[bold red]✘[/bold red]  Asset name '{target}' not found in registry.",
                        title="[bold red]Asset Error[/bold red]",
                        border_style="red",
                        width=term_width
                    )
                )
                raise SystemExit(1)
                
            manager.install_assets(target, is_group=False, keep_path=keep)

    except Exception as e:
        _handle_error(e)
