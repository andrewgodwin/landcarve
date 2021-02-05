import os
import shutil
import shlex
import subprocess
import sys
import tempfile

import click

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option("--extension", default=".stl")
@click.argument("pipeline_file")
@click.argument("input_paths", nargs=-1)
def pipeline(input_paths, extension, pipeline_file):
    """
    Runs a series of commands from a predefined pipeline, handling file passing.
    """
    temporary_file_counter = 1
    input_is_temporary = False
    # Load the pipeline file into memory
    click.echo("Pipeline: %s" % pipeline_file, err=True)
    pipeline = []
    for line in open(pipeline_file):
        # Skip blank lines and comments
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pipeline.append(line)
    # For each input...
    for input_path in input_paths:
        click.echo(click.style(f"Running on {input_path}", fg="blue", bold=True))
        # Run through the pipeline
        current_path = input_path
        with tempfile.TemporaryDirectory(prefix="landcarve-") as tmpdir:
            for i, line in enumerate(pipeline):
                # Work out input/output filenames
                if i == len(pipeline) - 1:
                    next_path = input_path + extension
                else:
                    next_path = os.path.join(
                        tmpdir, "output-%i.tmp" % temporary_file_counter
                    )
                    temporary_file_counter += 1
                # Run the command
                command = ["landcarve", *shlex.split(line), current_path, next_path]
                click.echo(click.style("Running: %s" % command, fg="green", bold=True))
                try:
                    subprocess.check_call(command)
                except subprocess.CalledProcessError:
                    click.echo(click.style("Subcommand failed", fg="red", bold=True))
                    sys.exit(1)
                # Delete any old temporary file
                if input_is_temporary:
                    os.unlink(current_path)
                current_path = next_path
                input_is_temporary = True
