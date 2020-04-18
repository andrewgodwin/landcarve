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
@click.argument("pipeline_file")
@click.argument("input_path")
@click.argument("output_path")
def pipeline(input_path, output_path, pipeline_file):
    """
    Runs a series of commands from a predefined pipeline, handling file passing.
    """
    temporary_file_counter = 1
    input_is_temporary = False
    current_path = input_path
    # Load the pipeline file and run through each command
    click.echo("Pipeline: %s" % pipeline_file, err=True)
    with tempfile.TemporaryDirectory(prefix="landcarve-") as tmpdir:
        for line in open(pipeline_file):
            # Skip blank lines and comments
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Work out input/output filenames
            next_path = os.path.join(tmpdir, "output-%i.tmp" % temporary_file_counter)
            temporary_file_counter += 1
            # Run the command
            command = ["landcarve", *shlex.split(line), current_path, next_path]
            click.echo(click.style("Running: %s" % line, fg="green", bold=True))
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
        # Save final file
        shutil.move(current_path, output_path)
