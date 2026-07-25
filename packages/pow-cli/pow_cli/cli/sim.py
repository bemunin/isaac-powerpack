"""Sim command implementation."""

import click
from rich.panel import Panel
from ..common.utils import console
from ..core.models.pow_config import PowConfig
from ..core.runner import Runner


@click.command(
    name="sim",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "-v",
    "--version",
    "sim_version",
    default=PowConfig.ISAACSIM_VERSION,
    show_default=True,
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
def sim_cmd(ctx: click.Context, sim_version: str, ros_bridge: str, no_ros: bool):
    """Run Isaac Sim from any directory, ignoring pow.toml.

    \b
    Unlike `pow run` this needs no project: no pyproject.toml is required and
    pow.toml is never read. Every unrecognized argument is forwarded verbatim
    to .pow/isaacsim/<version>/isaac-sim.sh.

    \b
    Examples:
      pow sim
      pow sim --no-ros
      pow sim -- --no-window --/renderer/enabled=gpu
    """
    try:
        Runner.run_sim(
            version=sim_version,
            ros_bridge=None if no_ros else ros_bridge,
            extra_args=ctx.args,
        )
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
