"""Ros command implementation."""

import click
from rich.panel import Panel
from ..common.utils import console
from ..core.ros_manager import RosManager


@click.command(
    name="ros",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show detailed feedback during container launch.")
@click.pass_context
def ros_cmd(ctx: click.Context, verbose: bool):
    """Launch the Isaac Sim ROS workspace docker container.

    Starts an interactive bash session inside the pow_simros_<distro>
    container built during `pow init`.

    \b
    Requires:
      - ROS integration enabled in pow.toml (enable_ros = true).
      - The pow_simros Docker image built via `pow init`.

    Any unrecognized arguments are passed as the container command.
    """
    extra_args = ctx.args or None
    try:
        RosManager.run_simros_container(extra_args=extra_args, verbose=verbose)
    except click.ClickException:
        raise
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]✘[/bold red]  {e}",
                title="[bold red]ROS Error[/bold red]",
                border_style="red",
            )
        )
        raise SystemExit(1)
