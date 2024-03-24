import click
import time
import PIL.Image
from concurrent.futures import ThreadPoolExecutor

from landcarve.cli import main
from landcarve.utils.coords import latlong_to_xy, xy_to_latlong
from landcarve.utils.io import download_image, save_geotiff, save_png


@main.command()
@click.option("--zoom", type=int, default=13)
@click.option("--invert-y/--no-invert-y", default=False)
@click.option("--delay", type=float, default=0)
@click.option("--concurrency", type=int, default=5)
@click.option("--tilesize", type=int, default=256)
@click.option("--raw", type=bool, is_flag=True, default=False)
@click.argument("coords")
@click.argument("output_path")
@click.argument("xyz_url")
def tileimage(
    coords, output_path, xyz_url, zoom, invert_y, delay, tilesize, raw, concurrency
):
    """
    Fetches tiles from an XYZ server and outputs a georeferenced image (of whole tiles)
    """
    tile_size = (tilesize, tilesize)
    # Extract coordinates
    lat1, long1, lat2, long2 = [float(n) for n in coords.lstrip(",").split(",")]
    # Turn those into tile coordinates, ensuring correct ordering
    if raw:
        x1, y1, x2, y2 = int(lat1), int(long1), int(lat2), int(long2)
    else:
        x1, y2 = latlong_to_xy(lat1, long1, zoom)
        x2, y1 = latlong_to_xy(lat2, long2, zoom)
    if x1 > x2:
        x2, x1 = x1, x2
    if y1 > y2:
        y2, y1 = y1, y2
    x_size = x2 - x1 + 1
    y_size = y2 - y1 + 1
    click.echo(f"X range: {x1} - {x2} ({x_size})   Y range: {y1} - {y2} ({y_size})")
    # Make a canvas that will fit them all
    image = PIL.Image.new("RGB", (tile_size[0] * x_size, tile_size[1] * y_size))
    # Download in parallel
    executor = ThreadPoolExecutor(max_workers=concurrency)
    futures = []
    images = {}
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            # If invert-y mode is on, flip image download path
            if invert_y:
                max_y = 2**zoom
                url = (
                    xyz_url.replace("{x}", str(x))
                    .replace("{y}", str(max_y - y))
                    .replace("{z}", str(zoom))
                )
            else:
                url = (
                    xyz_url.replace("{x}", str(x))
                    .replace("{y}", str(y))
                    .replace("{z}", str(zoom))
                )
            futures.append(executor.submit(download_tile, url, images, x, y, delay))
        click.echo("")
    # Show download progress
    while futures:
        futures = [f for f in futures if not f.done()]
        print_progress_grid(x1, y1, x2, y2, images)
        time.sleep(1)
    executor.shutdown()
    # Build image
    click.echo("Building image...")
    for (x, y), tile in images.items():
        assert tile.size == tile_size, f"Downloaded tile has wrong size {tile.size}"
        image.paste(tile, ((x - x1) * tile_size[0], (y - y1) * tile_size[1]))
    # Save the image
    if raw:
        save_png(image, output_path)
    else:
        # Work out the lat/long bounds of the downloaded tiles
        top_left = xy_to_latlong(x1, y1, zoom)
        bottom_right = xy_to_latlong(x2 + 1, y2 + 1, zoom)
        save_geotiff(
            image,
            top_left[1],
            top_left[0],
            bottom_right[1],
            bottom_right[0],
            output_path,
        )


def download_tile(url, images, x, y, delay):
    images[x, y] = download_image(url)
    time.sleep(delay)


def print_progress_grid(x1, y1, x2, y2, images, wipe_previous=False):
    for y in range(y1, y2 + 1):
        click.echo("[", nl=False)
        for x in range(x1, x2 + 1):
            if (x, y) in images:
                click.echo("#", nl=False)
            else:
                click.echo(".", nl=False)
        click.echo("]")
    click.echo()
