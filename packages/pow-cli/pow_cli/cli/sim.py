"""Sim command implementation."""

import click
from rich.panel import Panel
from ..common.utils import console
from ..core.models.pow_config import PowConfig
from ..core.runner import Runner


def _default_sim_version() -> str:
    """Version used when ``-v`` is omitted.

    Precedence: ``[sim] default_version`` in ``<global>/system.toml``, then
    whatever is actually installed (the newest when several are).  click
    evaluates a callable default at parse time, so both the file read and the
    scan of ``<global>/isaacsim`` happen per invocation rather than at import.
    """
    pinned = PowConfig.configured_default_version()
    if not pinned:
        return PowConfig.resolve_installed_version()

    installed = PowConfig.installed_versions()
    # With nothing installed at all, honour the pin so the Runner's own
    # "not found" error names the version the user asked for.
    if installed and pinned not in installed:
        fallback = PowConfig.resolve_installed_version()
        console.print(
            f"[yellow]⚠[/yellow]  system.toml pins Isaac Sim {pinned}, which is "
            f"not installed; using {fallback}."
        )
        return fallback
    return pinned


def _guarded(action, **kwargs):
    """Run a Runner action, rendering unexpected errors as a Sim Error panel."""
    try:
        action(**kwargs)
    except click.ClickException:
        raise
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]✘[/bold red]  {e}",
                title="[bold red]Sim Error[/bold red]",
                border_style="red",
            )
        )
        raise SystemExit(1)


class SimGroup(click.Group):
    """Group that falls through to `launch` for unrecognized arguments."""

    def resolve_command(self, ctx, args):
        if args and self.get_command(ctx, args[0]) is not None:
            return super().resolve_command(ctx, args)
        launch = self.get_command(ctx, "launch")
        return launch.name, launch, args

    def format_options(self, ctx, formatter):
        """List `launch`'s options as the group's own.

        Bare `pow sim` accepts them through :meth:`resolve_command`, so they
        belong in `pow sim --help` too - declared once, on `launch_cmd`.
        """
        launch = self.get_command(ctx, "launch")
        rows = []
        for param in launch.get_params(ctx):
            if param.name == "help":
                continue
            record = param.get_help_record(ctx)
            if record is not None:
                rows.append(record)
        for param in self.get_params(ctx):
            record = param.get_help_record(ctx)
            if record is not None:
                rows.append(record)
        if rows:
            with formatter.section("Options"):
                formatter.write_dl(rows)
        self.format_commands(ctx, formatter)


@click.group(
    name="sim",
    cls=SimGroup,
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True},
)
@click.pass_context
def sim_group(ctx: click.Context):
    """Run Isaac Sim from any directory, ignoring pow.toml.

    \b
    Unlike `pow run` this needs no project: no pyproject.toml is required and
    pow.toml is never read. Every unrecognized argument is forwarded verbatim
    to .pow/isaacsim/<version>/isaac-sim.sh.

    \b
    The version is resolved in this order:
      1. the -v/--version option
      2. [sim] default_version in .pow/system.toml
      3. the newest version installed under .pow/isaacsim/

    \b
    Subcommands:
      launch  Explicitly launch Isaac Sim (same as bare `pow sim`).
      check   Run the Isaac Sim compatibility check.

    \b
    Examples:
      pow sim
      pow sim --no-ros
      pow sim -v 5.1.0
      pow sim -- --no-window --/renderer/enabled=gpu
      pow sim check
    """
    if ctx.invoked_subcommand is None:
        _guarded(
            Runner.run_sim,
            version=_default_sim_version(),
            ros_bridge=PowConfig.ROS_BRIDGE,
            extra_args=[],
        )


@sim_group.command(
    name="launch",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "-v",
    "--version",
    "sim_version",
    default=_default_sim_version,
    show_default="system.toml, else the installed version",
    help="Isaac Sim version to run.",
)
@click.option(
    "--ros",
    "ros_bridge",
    type=click.Choice(PowConfig.SUPPORTED_ROS_BRIDGES),
    default=PowConfig.ROS_BRIDGE,
    show_default=True,
    help="ROS 2 bridge distro to load into the environment.",
)
@click.option(
    "--no-ros",
    is_flag=True,
    default=False,
    help="Launch without the ROS 2 bridge environment.",
)
@click.pass_context
def launch_cmd(ctx: click.Context, sim_version: str, ros_bridge: str, no_ros: bool):
    """Launch Isaac Sim, forwarding extra args to isaac-sim.sh."""
    _guarded(
        Runner.run_sim,
        version=sim_version,
        ros_bridge=None if no_ros else ros_bridge,
        extra_args=ctx.args,
    )


@sim_group.command(
    name="check",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "-v",
    "--version",
    "sim_version",
    default=_default_sim_version,
    show_default="system.toml, else the installed version",
    help="Isaac Sim version to check.",
)
@click.pass_context
def check_cmd(ctx: click.Context, sim_version: str):
    """Run the Isaac Sim compatibility check.

    \b
    Runs .pow/isaacsim/<version>/isaac-sim.compatibility_check.sh, which
    reports whether this machine meets the Isaac Sim requirements. Needs no
    project, and the script builds its own ROS environment - forward
    `-- --no-ros-env` to skip that step.
    """
    _guarded(Runner.run_sim_check, version=sim_version, extra_args=ctx.args)
