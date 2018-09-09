#!/usr/bin/env python3
"""
Takes raster layers, and fits them within a certain number of XY steps and
Z sizing, ready for passing to a 3D model creator.
"""

import click
import numpy
from osgeo import gdal


@click.command()
@click.option(
    "-x",
    "--xy-steps",
    default=1000,
    type=int,
    help="The maximum number of steps on X and Y.",
)
@click.option("--nodata", default=-1000.0, help="NODATA value.")
@click.argument("input_path")
@click.argument("output_path")
def main(input_path, output_path, xy_steps, z_scale, nodata, out_nodata):
    """
    Main command entry point.
    """
    # Load the file using GDAL
    raster = gdal.Open(input_path)
    # Extract band 1 into an array
    band = raster.GetRasterBand(1)
    arr = band.ReadAsArray()
    # Downsample it
    arr = downsample_array(arr, xy_steps)
    click.echo("Downsampled to {} x {}".format(arr.shape[0], arr.shape[1]))
    # Work out what the range of Z values is, ignoring NODATA
    if z_scale:
        min_value, max_value = value_range(arr, nodata)
        value_delta = max_value - min_value
        click.echo(
            "Value range: {} to {} ({})".format(min_value, max_value, value_delta)
        )
        # Scale the array to be more normalised
        scaler = (
            lambda x: (((x - min_value) / value_delta) * z_scale)
            if x > nodata
            else out_nodata
        )
        arr = numpy.vectorize(scaler)(arr)
        click.echo("Array scaled to range {} to {}".format(0, z_scale))
    # Write out the array
    driver = gdal.GetDriverByName("GTiff")
    outdata = driver.Create(
        output_path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32
    )
    outband = outdata.GetRasterBand(1)
    outband.SetNoDataValue(out_nodata)
    outband.WriteArray(arr)
    outband.FlushCache()


def downsample_array(arr, max_dimension):
    """
    Takes an array and downsamples it so its longest dimension is less than
    or equal to max_dimension.
    """
    # Work out the downsampling factors for that array
    width, height = arr.shape
    current_steps = max(width, height)
    downsample_factor = 1
    while (current_steps // downsample_factor) > max_dimension:
        downsample_factor += 1
    click.echo(
        "Array size {} x {} - downsample factor {}".format(
            width, height, downsample_factor
        )
    )
    # Downsample the array
    return arr[::downsample_factor, ::downsample_factor]


def value_range(arr, nodata):
    """
    Given an array and a nodata limit, returns the range of values in the array.
    """
    min_value = max_value = None
    for value in numpy.nditer(arr):
        if value > nodata:
            if min_value is None or value < min_value:
                min_value = value
            if max_value is None or value > max_value:
                max_value = value
    return min_value, max_value


if __name__ == "__main__":
    main()
