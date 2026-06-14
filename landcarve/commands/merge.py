import click
from osgeo import gdal

from landcarve.cli import main


@main.command()
@click.argument("input_paths", nargs=-1)
@click.argument("output_path")
def merge(
    input_paths,
    output_path,
):
    """
    Merges DEMs together
    """
    # Mosaic all the inputs into a single output raster
    gdal.Warp(output_path, list(input_paths))
