import math


def latlong_to_xy(lat, long, zoom):
    """
    Converts a latitude and longitude into tile X and Y coords
    """
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = int((long + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def xy_to_latlong(x, y, zoom):
    n = 2.0**zoom
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg
