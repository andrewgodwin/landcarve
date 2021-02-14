import click
import subprocess

from landcarve.cli import main


@main.command()
@click.argument("input_paths", nargs=-1)
@click.argument("output_path")
def merge(
    input_paths, output_path,
):
    """
    Merges DEMs together
    """

    subprocess.call(["gdal_merge.py", "-o", output_path] + list(input_paths))
