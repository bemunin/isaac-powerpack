"""Pow CLI - Root commands."""

import click

from .init import init_cmd
# from .add import add_group
from .check import check_cmd
from .lint import lint_group
from .run import run_cmd
from .sim import sim_cmd
from .ros import ros_group
from .python import python_cmd
from .asset import asset_group


@click.group()
@click.version_option(
    None,
    "-v",
    "--version",
    package_name="pow-cli",
    prog_name="pow",
    message="%(prog)s %(version)s",
    help="Show the pow CLI version.",
)
def pow_group():
    """Manage Isaac Sim projects and simplify the development workflow."""
    pass


# Register commands
pow_group.add_command(init_cmd)
pow_group.add_command(check_cmd)
pow_group.add_command(lint_group)
pow_group.add_command(run_cmd)
pow_group.add_command(sim_cmd)
pow_group.add_command(ros_group)
pow_group.add_command(python_cmd)
pow_group.add_command(asset_group)
