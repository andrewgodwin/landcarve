#!/usr/bin/env python3
"""
Runs a series of commands in-order to produce a result, automatically carrying
the output files down the chain
"""

import click
import subprocess


@click.argument("pipeline")
@click.argument("input_path")
@click.argument("output_path")
def main(pipeline, input_path, output_path):
    """
    Main command entry point.
    """
    # Temporary file name counter
    temporary_file_counter = 1
    current_path = input_path
    # Load the pipeline file and run through each command
    for line in open(pipeline):
        # Skip blank lines and comments
        if not line.strip() or line.startswith("#"):
            continue
        # Work out input/output filenames
        next_path = "output-%i.tmp" % temporary_file_counter
        temporary_file_counter += 1
        # Run the command
        print("\033[92mRunning %s\033[0m" % line)
        subprocess.check_call(
            "python3 %s %s %s" % (line, current_path, next_path), shell=True
        )
        current_path = next_path
    # Save final file
    os.rename(current_path, output_path)


if __name__ == "__main__":
    main()
