import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.argument("input_path")
@click.argument("output_path")
def flipy(input_path, output_path):
    """
    Flips the image's up and down
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Run stepper
    arr = numpy.flipud(arr)
    click.echo("Array flipped up/down")
    # Write out the array
    array_to_raster(arr, output_path)
