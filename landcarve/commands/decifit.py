import click

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "-x",
    "--xy-steps",
    default=1000,
    type=int,
    help="The maximum number of steps on X and Y.",
)
@click.argument("input_path")
@click.argument("output_path")
def decifit(input_path, output_path, xy_steps):
    """
    Scales raster layers down to a certain number of cells in X/Y, maintaining
    aspect ratio.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Downsample it
    arr = downsample_array(arr, xy_steps)
    click.echo("Downsampled to {} x {}".format(arr.shape[0], arr.shape[1]), err=True)
    # Write out the array
    array_to_raster(arr, output_path)


def downsample_array(arr, max_dimension):
    """
    Takes an array and downsamples it so its longest dimension is less than
    or equal to max_dimension.
    """
    # Work out the downsampling factors for that array
    width, height = arr.shape
    current_steps = max(width, height)
    downsample_factor = 1
    while (current_steps // downsample_factor) > max_dimension:
        downsample_factor += 1
    # Downsample the array
    return arr[::downsample_factor, ::downsample_factor]
