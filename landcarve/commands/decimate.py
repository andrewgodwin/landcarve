import click

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "-d",
    "--divisor",
    default=2,
    type=int,
    help="The divisor on number of steps",
)
@click.argument("input_path")
@click.argument("output_path")
def decimate(input_path, output_path, divisor):
    """
    Scales raster layers down to a certain number of cells in X/Y, maintaining
    aspect ratio.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Downsample it
    arr = arr[::divisor, ::divisor]
    click.echo("Downsampled to {} x {}".format(arr.shape[0], arr.shape[1]), err=True)
    # Write out the array
    array_to_raster(arr, output_path)
