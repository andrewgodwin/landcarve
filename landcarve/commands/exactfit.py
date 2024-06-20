import click
import numpy

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "-x",
    "--x-steps",
    default=1000,
    type=int,
    help="The exact number of steps on X",
)
@click.option(
    "-y",
    "--y-steps",
    default=1000,
    type=int,
    help="The exact number of steps on Y",
)
@click.argument("input_path")
@click.argument("output_path")
def exactfit(input_path, output_path, x_steps, y_steps):
    """
    Scales raster layers down to a certain number of cells in X/Y exactly.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Downsample it
    arr = downsample_array(arr, x_steps, y_steps)
    click.echo("Downsampled to {} x {}".format(arr.shape[0], arr.shape[1]), err=True)
    # Write out the array
    array_to_raster(arr, output_path)


def downsample_array(arr, x_dimension, y_dimension):
    """
    Takes an array and downsamples it so its longest dimension is less than
    or equal to max_dimension.
    """
    # Work out the downsampling factors for that array
    current_y, current_x = arr.shape
    x_step = current_x / x_dimension
    y_step = current_y / y_dimension
    # Create a new array and populate it
    new_arr = numpy.ndarray((y_dimension, x_dimension))
    for dx in range(x_dimension):
        for dy in range(y_dimension):
            new_arr[dy][dx] = arr[int(dy * y_step)][int(dx * x_step)]
    return new_arr
