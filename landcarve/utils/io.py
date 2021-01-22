import io
import PIL.Image
import os
import subprocess
import requests
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


def array_to_raster(arr, output_path, offset_and_pixel=None, projection=None):
    """
    Takes a NumPy array and outputs it to a GDAL file.

    offset_and_pixel is (x offset, y offset, pixel width, pixel height)
    """
    if output_path == "-":
        output_path = "/dev/stdout"
    driver = gdal.GetDriverByName("GTiff")
    outdata = driver.Create(
        output_path,
        xsize=arr.shape[1],
        ysize=arr.shape[0],
        bands=1,
        eType=gdal.GDT_Float32,
    )
    # Set projection and transform if we have them
    if offset_and_pixel:
        outdata.SetGeoTransform(
            [
                offset_and_pixel[0],  # X offset
                offset_and_pixel[2],  # Pixel width
                0,  # Rotation coefficient 1
                offset_and_pixel[1],  # Y offset
                0,  # Rotation coefficient 2
                offset_and_pixel[3],  # Pixel height
            ]
        )
    if projection:
        outdata.SetProjection(projection)
    outband = outdata.GetRasterBand(1)
    # TODO: Use global nodata value?
    outband.SetNoDataValue(-1000)
    outband.WriteArray(arr)
    outband.FlushCache()


def download_image(url):
    """
    Downloads a URL into an Image object
    """
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError("Cannot download URL %s: %s" % (url, r.content))
    return PIL.Image.open(io.BytesIO(r.content))


def save_geotiff(image, x1, y1, x2, y2, path, proj="EPSG:4326"):
    """
    Saves an image as a GeoTIFF with the given coordinates as the corners.
    """
    # Save image out
    temp_path = path + ".temp.png"
    image.save(temp_path)
    # Use gdal_translate to add GCPs
    subprocess.check_call(
        [
            "gdal_translate",
            "-a_ullr",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            "-a_srs",
            proj,
            "-of",
            "GTiff",
            temp_path,
            path,
        ]
    )
    # Delete temp file
    os.unlink(temp_path)
