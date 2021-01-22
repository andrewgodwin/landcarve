import itertools
import sys

import click
import PIL.Image
import laspy.file
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster


@main.command()
@click.option(
    "-x",
    "--xy-steps",
    default=1000,
    type=int,
    help="The maximum number of steps on X and Y.",
)
@click.option("-s", "--snap", default=1, type=int, help="Snap/thinning resolution")
@click.argument("input_path")
@click.argument("output_path")
def lasdem(input_path, output_path, xy_steps, snap):
    """
    Turns a raw .las or .laz file into a DEM
    """
    # Open the LAS file
    las = laspy.file.File(input_path, mode="r")
    # For each point, bucket it into the nearest snap coord
    points = numpy.vstack((las.x, las.y, las.z)).T
    snaps = {}
    min_x, max_x, min_y, max_y = None, None, None, None
    with click.progressbar(length=points.shape[0], label="Thinning LAS") as bar:
        for x, y, z in points:
            bar.update(1)
            new_x = int(x // snap)
            new_y = int(y // snap)
            # Work out highest elevation
            if (new_x, new_y) in snaps:
                snaps[new_x, new_y] = max(snaps[new_x, new_y], z)
            else:
                snaps[new_x, new_y] = z
            # Update bounds
            if min_x is None or min_x > new_x:
                min_x = new_x
            if max_x is None or max_x < new_x:
                max_x = new_x
            if min_y is None or min_y > new_y:
                min_y = new_y
            if max_y is None or max_y < new_y:
                max_y = new_y
    # Calculate the size of the final array (we don't trust the .las headers)
    x_index = lambda v: int((v - min_x) // snap)
    y_index = lambda v: int((v - min_y) // snap)
    x_size = x_index(max_x) + 1
    y_size = y_index(max_y) + 1
    # Create a new array to hold the data
    click.echo(f"Creating DEM ({x_size}x{y_size})")
    arr = numpy.full((x_size, y_size), NODATA, dtype=numpy.double)
    for (x, y), z in snaps.items():
        arr[x_index(x), y_index(y)] = z
    # Fill any voids by finding their nearest neighbour
    with click.progressbar(length=x_size * y_size, label="Filling voids") as bar:
        for x in range(arr.shape[0]):
            for y in range(arr.shape[1]):
                bar.update(1)
                if arr[x][y] <= NODATA:
                    arr[x][y] = find_nearest_neighbour(arr, x, y)
    # Write out a TIF
    array_to_raster(arr, output_path)


def find_nearest_neighbour(arr, x, y):
    """
    Finds the nearest non-NODATA value to x, y
    """
    for distance in range(100):
        for dx, dy in [
            (1, 0),
            (0, 1),
            (-1, 0),
            (0, -1),
            (1, 1),
            (1, -1),
            (-1, -1),
            (-1, 1),
        ]:
            new_x = x + (dx * distance)
            new_y = y + (dy * distance)
            if (
                new_x >= 0
                and new_x < arr.shape[0]
                and new_y >= 0
                and new_y < arr.shape[1]
                and arr[new_x][new_y] > NODATA
            ):
                return arr[new_x][new_y]
    return NODATA
