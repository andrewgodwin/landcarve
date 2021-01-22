import sys

import click
import laspy.file
import numpy
from osgeo import osr

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster


@main.command()
@click.option("-s", "--snap", default=1, type=int, help="Snap/thinning resolution")
@click.option(
    "-d",
    "--void-distance",
    default=10,
    type=int,
    help="Max distance to try and fill voids from",
)
@click.argument("input_paths", nargs=-1)
@click.argument("output_path")
def lasdem(input_paths, output_path, snap, void_distance):
    """
    Turns a raw .las or .laz file into a DEM
    """
    # Check there's valid input due to nargs
    if not input_paths:
        click.echo("You must provide at least one input file")
        sys.exit(1)

    # Open the LAS files
    las_files = [laspy.file.File(input_path, mode="r") for input_path in input_paths]

    # Work out the projection
    projection = None
    for las in las_files:
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
            click.echo(f"Mismatched projections - {las} does not match the first file")

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
    x_index = lambda v: int((v - min_x) // snap)
    y_index = lambda v: int((v - min_y) // snap)
    x_size = x_index(max_x) + 1
    y_size = y_index(max_y) + 1

    # Print some diagnostic info
    click.echo(f"X range: {min_x} - {max_x}  Y range: {min_y} - {max_y}")
    click.echo(f"Final DEM size {x_size}x{y_size}")

    # Create a new array to hold the data
    arr = numpy.full((x_size, y_size), NODATA, dtype=numpy.float)

    # For each point, bucket it into the right array coord
    with click.progressbar(length=num_points, label="Thinning") as bar:
        for las in las_files:
            points = numpy.vstack((las.x, las.y, las.z)).T
            for x, y, z in points:
                bar.update(1)
                new_x = x_index(x)
                new_y = y_index(y)
                arr[new_y][new_x] = max(arr[new_y][new_x], z)

    # Fill any voids by finding their nearest neighbour
    void_fills = []
    with click.progressbar(length=x_size * y_size, label="Filling voids") as bar:
        for x in range(arr.shape[0]):
            for y in range(arr.shape[1]):
                bar.update(1)
                if arr[x][y] <= NODATA:
                    void_fills.append(
                        (
                            x,
                            y,
                            find_nearest_neighbour(arr, x, y, distance=void_distance),
                        )
                    )

    # We write void fills back separately so they don't interfere with each other
    for x, y, z in void_fills:
        if z > 2000:
            click.echo(x, y, z)
        arr[x][y] = z

    # Write out a TIF
    array_to_raster(
        arr,
        output_path,
        offset_and_pixel=(min_x, min_y, snap, snap),
        projection=projection,
    )


def find_nearest_neighbour(arr, x, y, distance=10):
    """
    Finds the nearest non-NODATA value to x, y
    """
    for d in range(distance):
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
            new_x = x + (dx * d)
            new_y = y + (dy * d)
            if (
                new_x >= 0
                and new_x < arr.shape[0]
                and new_y >= 0
                and new_y < arr.shape[1]
                and arr[new_x][new_y] > NODATA
            ):
                return arr[new_x][new_y]
    return NODATA
