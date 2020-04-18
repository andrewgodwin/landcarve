import click
import numpy

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array


@main.command()
@click.option(
    "--factor", default=1.0, type=float, help="Smoothing factor",
)
@click.argument("input_path")
@click.argument("output_path")
def smooth(input_path, output_path, factor):
    """
    Scales raster layers down to a certain number of cells in X/Y, maintaining
    aspect ratio.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)

    smooth_offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    factor = float(factor)
    with click.progressbar(length=arr.shape[0], label="Smoothing heightmap") as bar:
        for index, value in numpy.ndenumerate(arr):
            if index[1] == 0:
                bar.update(1)
            # Fetch surrounding heights
            others = []
            for offset in smooth_offsets:
                neighbour_index = index[0] + offset[0], index[1] + offset[1]
                if not (
                    neighbour_index[0] < 0
                    or neighbour_index[0] >= arr.shape[0]
                    or neighbour_index[1] < 0
                    or neighbour_index[1] >= arr.shape[1]
                ):
                    others.append(arr[neighbour_index])
            # Clip height to at most 1 stdev from the other heights
            m = mean(others)
            s = pstdev(others)
            limit = s * (1 / factor)
            arr[index] = clip(value, m - limit, m + limit)

    # Write out the array
    click.echo("Smoothed with factor %s" % factor, err=True)
    array_to_raster(arr, output_path)


def clip(x, lower, upper):
    return min(upper, max(lower, x))


def mean(data):
    """Return the sample arithmetic mean of data."""
    n = len(data)
    if n < 1:
        raise ValueError("mean requires at least one data point")
    return sum(data) / float(n)


def _ss(data):
    """Return sum of square deviations of sequence data."""
    c = mean(data)
    ss = sum((x - c) ** 2 for x in data)
    return ss


def pstdev(data):
    """Calculates the population standard deviation."""
    n = len(data)
    if n < 2:
        raise ValueError("variance requires at least two data points")
    ss = _ss(data)
    pvar = ss / n  # the population variance
    return pvar ** 0.5
