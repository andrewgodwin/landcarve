import click
import numpy

from landcarve.cli import main
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.argument("input_path")
@click.argument("output_path")
@click.argument("elevation_path")
@click.option(
    "-m",
    "--min-value",
    type=int,
    help="Minimum value to preserve (inclusive)",
)
@click.option(
    "-x",
    "--max-value",
    type=int,
    help="Maximum value to preserve (inclusive)",
)
def elevalue(input_path, output_path, elevation_path, min_value, max_value):
    """
    Takes a raster layer with discrete values, and a raster layer with
    continuous elevation values, and outputs elevation only where the discrete
    values match certain numbers (for landcover, water etc.)
    """
    # Load the values file using GDAL
    values_arr = raster_to_array(input_path)
    # Load the elevation file using GDAL
    elevation_arr = raster_to_array(elevation_path)
    # Go through the values array and create a new array where things match with elevation
    x_step = elevation_arr.shape[0] / values_arr.shape[0]
    y_step = elevation_arr.shape[1] / values_arr.shape[1]

    # Create the value test function
    def has_value(dx, dy) -> bool:
        test = lambda dx, dy: min_value <= values_arr[dx][dy] <= max_value
        if not test(dx, dy):
            return False
        num_neighbours = 0
        for ox, oy in [
            (dx - 1, dy - 1),
            (dx - 1, dy),
            (dx - 1, dy + 1),
            (dx, dy - 1),
            (dx, dy + 1),
            (dx + 1, dy - 1),
            (dx + 1, dy),
            (dx + 1, dy + 1),
        ]:
            if (
                ox < 0
                or oy < 0
                or ox >= values_arr.shape[0]
                or oy >= values_arr.shape[1]
            ):
                continue
            if test(ox, oy):
                num_neighbours += 1
            if num_neighbours >= 3:
                return True
        return False

    # Create a new array and populate it
    new_arr = numpy.ndarray(values_arr.shape)
    for dx in range(values_arr.shape[0]):
        for dy in range(values_arr.shape[1]):
            if has_value(dx, dy):
                new_arr[dx][dy] = elevation_arr[int(dx * x_step)][int(dy * y_step)]
            else:
                new_arr[dx][dy] = -1000
    click.echo(
        "Elevalued to {} x {}".format(new_arr.shape[0], new_arr.shape[1]), err=True
    )
    # Write out the array
    array_to_raster(new_arr, output_path)
