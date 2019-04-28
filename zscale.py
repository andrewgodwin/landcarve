#!/usr/bin/env python3
"""
Scales the Z axis (values) in a raster based on one of several algorithms.
"""

import click
import numpy
from osgeo import gdal


@click.command()
@click.option(
    "--fit",
    default=None,
    type=int,
    help="Scale linearly from 0 to specified maximum value",
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
