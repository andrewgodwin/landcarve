import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.argument("input_paths", nargs=-1)
def stats(input_paths):
    """
    Gives stats on a DEM
    """
    for input_path in input_paths:
        click.echo(click.style(f"{input_path}", fg="blue", bold=True))
        # Load the file using GDAL
        arr = raster_to_array(input_path)
        # Work out what the range of Z values is, ignoring NODATA
        min_value, max_value = value_range(arr, NODATA)
        value_delta = max_value - min_value
        click.echo(
            f"Z Value range: {min_value:.2f} to {max_value:.2f} ({value_delta:.2f})"
        )


def value_range(arr, NODATA=NODATA):
    """
    Given an array and a NODATA limit, returns the range of values in the array.
    """
    min_value = max_value = None
    for value in numpy.nditer(arr):
        value = value.item()
        if value > NODATA:
            if min_value is None or value < min_value:
                min_value = value
            if max_value is None or value > max_value:
                max_value = value
    return min_value, max_value
