import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "--fit",
    default=1.0,
    type=float,
    help="Scale linearly from 0 to specified maximum value",
)
@click.argument("input_path")
@click.argument("output_path")
def zfit(input_path, output_path, fit):
    """
    Scales raster layers down to a certain number of cells in X/Y, maintaining
    aspect ratio.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Work out what the range of Z values is, ignoring NODATA
    min_value, max_value = value_range(arr, NODATA)
    value_delta = max_value - min_value
    click.echo("Value range: {} to {} ({})".format(min_value, max_value, value_delta))
    # Scale the array to be more normalised
    scaler = lambda x: (((x - min_value) / value_delta) * fit) if x > NODATA else NODATA
    arr = numpy.vectorize(scaler, otypes="f")(arr)
    click.echo("Array scaled to range {} to {}".format(0, fit), err=True)
    # Write out the array
    array_to_raster(arr, output_path)


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
