from osgeo import gdal


def raster_to_array(input_path):
    """
    Takes an input raster file and turns it into a NumPy array.
    Only takes band 1 for now.
    """
    if input_path == "-":
        input_path = "/dev/stdin"
    raster = gdal.Open(input_path)
    band = raster.GetRasterBand(1)
    arr = band.ReadAsArray()
    return arr


def array_to_raster(arr, output_path):
    """
    Takes a NumPy array and outputs it to a GDAL file.
    """
    if output_path == "-":
        output_path = "/dev/stdout"
    driver = gdal.GetDriverByName("GTiff")
    outdata = driver.Create(
        output_path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32
    )
    outband = outdata.GetRasterBand(1)
    # TODO: Use global nodata value?
    outband.SetNoDataValue(-1000)
    outband.WriteArray(arr)
    outband.FlushCache()
