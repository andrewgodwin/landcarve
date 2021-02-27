import click

from skimage.morphology import area_closing, area_opening

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "--factor", default=1.0, type=float, help="Smoothing factor",
)
@click.argument("input_path")
@click.argument("output_path")
def smooth(input_path, output_path, factor):
    """
    Fancier smoothing
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)

    arr = area_closing(arr, area_threshold=32)
    arr = area_opening(arr, area_threshold=32)

    # Write out the array
    click.echo("Smooth2ed with factor %s" % factor, err=True)
    array_to_raster(arr, output_path)
