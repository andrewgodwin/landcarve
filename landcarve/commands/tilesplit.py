import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array_and_projection


@main.command()
@click.option(
    "--x-size",
    default=1000,
    type=int,
    help="Size of new tiles in X dimension",
)
@click.option(
    "--y-size",
    default=1000,
    type=int,
    help="Size of new tiles in Y dimension",
)
@click.option(
    "--x-offset",
    default=0,
    type=int,
    help="Offset of start point in X",
)
@click.option(
    "--y-offset",
    default=0,
    type=int,
    help="Offset of start point in Y",
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
    # Work out Y slice sizes
    y_slices = [0]
    while y_slices[-1] + y_size < arr.shape[0]:
        y_slices.append(y_slices[-1] + y_size)
    if y_slices[-1] < arr.shape[0]:
        y_slices.append(arr.shape[0])
    # Work out X slice sizes
    x_slices = [0]
    while x_slices[-1] + x_size < arr.shape[1]:
        x_slices.append(x_slices[-1] + x_size)
    if x_slices[-1] < arr.shape[1]:
        x_slices.append(arr.shape[1])
    # Slice and dice
    for y, y_next in zip(y_slices, y_slices[1:]):
        for x, x_next in zip(x_slices, x_slices[1:]):
            tile = arr[y:y_next, x:x_next]
            # Write out the tile
            array_to_raster(
                tile,
                f"{output_path}_{x}_{y}.tif",
                offset_and_pixel=(x, y, 1, 1),
                projection=proj,
            )
            click.echo(f"Wrote tile {x} {y}")
