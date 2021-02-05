import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array_and_projection


@main.command()
@click.option(
    "--x-size", default=1000, type=int, help="Size of new tiles in X dimension",
)
@click.option(
    "--y-size", default=1000, type=int, help="Size of new tiles in Y dimension",
)
@click.option(
    "--x-offset", default=0, type=int, help="Offset of start point in X",
)
@click.option(
    "--y-offset", default=0, type=int, help="Offset of start point in Y",
)
@click.argument("input_path")
@click.argument("output_path")
def tilesplit(input_path, output_path, x_size, y_size, x_offset, y_offset):
    """
    Splits a single big DEM into smaller ones
    """
    # Load the file using GDAL
    arr, proj = raster_to_array_and_projection(input_path)
    # Prep output path
    if output_path.endswith(".tif"):
        output_path = output_path[:-4]
    # Slice and dice
    y = y_offset
    while y + y_size <= arr.shape[0]:
        x = x_offset
        while x + x_size <= arr.shape[1]:
            tile = arr[y : y + y_size, x : x + x_size]
            # Write out the tile
            array_to_raster(
                tile,
                f"{output_path}_{x}_{y}.tif",
                offset_and_pixel=(x, y, 1, 1),
                projection=proj,
            )
            click.echo(f"Wrote tile {x} {y}")
            x += x_size
        y += y_size
