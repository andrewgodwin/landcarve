import functools
import sys

import click
import laspy.file
import numpy
from osgeo import osr

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster
from landcarve.commands.smooth import mean, pstdev, clip


@main.command()
@click.option("-s", "--snap", default=1, type=int, help="Snap/thinning resolution")
@click.option(
    "-d",
    "--void-distance",
    default=10,
    type=int,
    help="Max distance to try and fill voids from",
)
@click.option(
    "-z",
    "--z-limit",
    default=4000,
    type=int,
    help="Maximum elevation to trust; discard anything above",
)
@click.option(
    "-s",
    "--despeckle",
    default=1,
    type=int,
    help="Despeckle factor; higher is stronger. 0 to disable.",
)
@click.argument("input_paths", nargs=-1)
@click.argument("output_path")
def lasdem(input_paths, output_path, snap, void_distance, z_limit, despeckle):
    """
    Turns a raw .las or .laz file into a DEM
    """
    # Check there's valid input due to nargs
    if not input_paths:
        click.echo("You must provide at least one input file")
        sys.exit(1)

    # Work out the projection
    projection = None
    las_files = []
    with click.progressbar(length=len(input_paths), label="Opening files") as bar:
        for input_path in input_paths:
            bar.update(1)
            las = laspy.file.File(input_path, mode="r")
            las_files.append(las)
            las_projection = "unknown"
            for vlr in las.header.vlrs:
                if vlr.record_id == 34735:  # GeoTIFF tag format
                    num_tags = vlr.parsed_body[3]
                    for i in range(num_tags):
                        key_id = vlr.parsed_body[4 + (i * 4)]
                        offset = vlr.parsed_body[7 + (i * 4)]
                        if key_id == 3072:
                            srs = osr.SpatialReference()
                            srs.ImportFromEPSG(offset)
                            las_projection = srs.ExportToWkt()
                            break
            if projection is None or projection == las_projection:
                projection = las_projection
            else:
                click.echo(
                    f"Mismatched projections - {las} does not match the first file"
                )

    # Calculate the bounds of all files (initial values are a bit stupid)
    click.echo(f"{len(input_paths)} file(s) provided")
    min_x, max_x, min_y, max_y = 1000000000, -1000000000, 1000000000, -1000000000
    num_points = 0
    for las in las_files:
        num_points += las.points.shape[0]
        min_x = min(min_x, las.x.min())
        max_x = max(max_x, las.x.max())
        min_y = min(min_y, las.y.min())
        max_y = max(max_y, las.y.max())

    # Calculate the size of the final array
    x_index = functools.lru_cache(maxsize=10240)(lambda v: int((v - min_x) // snap))
    y_index = functools.lru_cache(maxsize=10240)(lambda v: int((v - min_y) // snap))
    x_size = x_index(max_x) + 1
    y_size = y_index(max_y) + 1

    # Print some diagnostic info
    click.echo(f"X range: {min_x} - {max_x}  Y range: {min_y} - {max_y}")
    click.echo(f"Final DEM size {x_size}x{y_size}")

    # Create a new array to hold the data
    arr = numpy.full((y_size, x_size), NODATA, dtype=numpy.float)

    # For each point, bucket it into the right array coord
    with click.progressbar(length=num_points, label="Thinning") as bar:
        n = 0
        for las in las_files:
            points = numpy.vstack((las.x, las.y, las.z)).T
            for i, (x, y, z) in enumerate(points):
                if z <= z_limit:
                    new_x = x_index(x)
                    new_y = y_index(y)
                    arr[new_y][new_x] = max(arr[new_y][new_x], z)
                n += 1
                if n > 1000:
                    bar.update(1000)
                    n = 0

    # Scan for all voids in the array
    voids = set()
    with click.progressbar(length=arr.shape[0], label="Discovering voids") as bar:
        for y in range(arr.shape[0]):
            bar.update(1)
            for x in range(arr.shape[1]):
                if arr[y][x] <= NODATA:
                    voids.add((x, y))

    # Fill any voids by finding their nearest neighbour
    num_voids = len(voids)
    with click.progressbar(length=void_distance, label="Filling voids") as bar:
        for _ in range(void_distance):
            bar.update(1)
            for x, y in list(voids):
                z = find_nearest_neighbour(arr, x, y)
                if z > NODATA:
                    arr[y][x] = z
                    voids.remove((x, y))
    click.echo("Removed %s / %s voids" % (num_voids - len(voids), num_voids))

    # Despeckle any single pixels that are weirdly high/low
    if despeckle:
        with click.progressbar(length=arr.shape[0], label="Despeckling") as bar:
            for y in range(arr.shape[0]):
                bar.update(1)
                for x in range(arr.shape[1]):
                    # Find its four direct neighbours and weight on their values
                    others = get_neighbours(arr, x, y)
                    if len(others) < 3:
                        continue
                    m = mean(others)
                    s = pstdev(others)
                    limit = s * (1 / despeckle)
                    if abs(arr[y][x] - m) > limit:
                        arr[y][x] = find_nearest_neighbour(arr, x, y)

    # Write out a TIF
    array_to_raster(
        arr,
        output_path,
        offset_and_pixel=(min_x, min_y, snap, snap),
        projection=projection,
    )


def get_neighbours(arr, x, y):
    """
    Finds the nearest non-NODATA value to x, y
    """
    values = []
    for dx, dy in [
        (1, 0),
        (0, 1),
        (-1, 0),
        (0, -1),
    ]:
        new_x = x + dx
        new_y = y + dy
        if (
            new_x >= 0
            and new_x < arr.shape[1]
            and new_y >= 0
            and new_y < arr.shape[0]
            and arr[new_y][new_x] > NODATA
        ):
            values.append(arr[new_y][new_x])
    return values


def find_nearest_neighbour(arr, x, y):
    """
    Finds the nearest non-NODATA value to x, y
    """
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
        new_x = x + dx
        new_y = y + dy
        if (
            new_x >= 0
            and new_x < arr.shape[1]
            and new_y >= 0
            and new_y < arr.shape[0]
            and arr[new_y][new_x] > NODATA
        ):
            return arr[new_y][new_x]
    return NODATA
