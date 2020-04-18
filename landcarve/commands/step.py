import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "--interval", default=10, type=float, help="Stepping interval",
)
@click.option(
    "--base", default=0, type=float, help="Offset for start of step",
)
@click.argument("input_path")
@click.argument("output_path")
def step(input_path, output_path, interval, base):
    """
    Snaps layer values to boundaries
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Run stepper
    scaler = lambda x: round(x / interval) * interval
    arr = numpy.vectorize(scaler, otypes="f")(arr)
    click.echo(
        "Array stepped with interval {}, base {}".format(interval, base), err=True
    )
    # Write out the array
    array_to_raster(arr, output_path)
