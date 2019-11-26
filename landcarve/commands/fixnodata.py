import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "--nodata",
    default=0,
    type=int,
    help="NODATA boundary for input",
)
@click.argument("input_path")
@click.argument("output_path")
@click.pass_context
def fixnodata(ctx, input_path, output_path, nodata):
    """
    Fixes NODATA ranges on files to pin them to -1000.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Fix NODATA
    scaler = (
        lambda x: x
        if x > nodata
        else NODATA
    )
    arr = numpy.vectorize(scaler)(arr)
    click.echo("NODATA values set to {}".format(NODATA), err=True)
    # Write out the array
    array_to_raster(arr, output_path)
