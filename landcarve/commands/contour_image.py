import click
import gdal
import numpy
import PIL.Image
import skimage.measure
import skimage.morphology
import simplification.cutil
import svgwrite

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import array_to_raster, raster_to_array
from landcarve.utils.graphics import bitmap_array_to_image, draw_border


@main.command()
@click.option(
    "--min-object",
    default=0.05,
    type=float,
    help="Size limit for objects in percent (any smaller than this will be ignored)",
)
@click.option(
    "--min-hole",
    default=0.02,
    type=float,
    help="Size limit for holes in percent (any smaller than this will be filled)",
)
@click.option(
    "--simp",
    default=0.5,
    type=float,
    help="Visvalingam-Whyatt simplification coefficient for contours",
)
@click.option(
    "--bleed",
    default=2,
    type=int,
    help="Number of pixels (on the input) to bleed over the image for cutting",
)
@click.argument("input_path")
@click.argument("output_path")
@click.argument("image_path")
@click.argument("contours")
def contour_image(
    input_path, output_path, image_path, contours, bleed, min_object, min_hole, simp
):
    """
    Slices a terrain into contour segments and then outputs an image and a cut
    line for each of the segments.

    If used in a pipeline, must be the final item as it uses the output path
    as a prefix.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Load the original image using Pillow
    image = PIL.Image.open(image_path).convert(mode="RGBA")
    # Check contour list
    contour_list = sorted(
        [int(x) if int(x) == float(x) else float(x) for x in contours.split(",")]
    )
    contour_list.append(99999999999)
    if len(contour_list) < 3:
        raise ValueError("You must pass at least 2 contour boundaries")
    # Slice per contour pair for the cuts
    terrains = {}
    click.echo("Processing cuts")
    for lower, upper in zip(contour_list, contour_list[1:]):
        terrains[lower] = make_cuts(
            arr,
            lower,
            upper,
            output_path,
            min_object=min_object,
            min_hole=min_hole,
            simp=simp,
        )
    # Now do the images
    click.echo("Processing images")
    for lower, upper in zip(contour_list, contour_list[1:]):
        make_image(arr, terrains, lower, upper, image, output_path, bleed=bleed)


def make_cuts(arr, lower, upper, output_path, min_object, min_hole, simp):
    """
    Calculates the cut lines for one contour range.
    """
    # Turn the array into a bitmap of "is it at or above" for the image calculation
    terrain = numpy.vectorize(lambda x: lower <= x, otypes="?")(arr)

    # Fill small holes
    hole_threshold = int(terrain.shape[0] * terrain.shape[1] * 0.01 * min_hole)
    object_threshold = int(terrain.shape[0] * terrain.shape[1] * 0.01 * min_object)
    terrain = skimage.morphology.remove_small_holes(
        terrain, area_threshold=hole_threshold, in_place=True
    )
    terrain = skimage.morphology.remove_small_objects(
        terrain, min_size=object_threshold, in_place=True
    )

    # Trace contours on that filled terrain
    contours = skimage.measure.find_contours(terrain, 0.5)

    # Write out final SVG with cuts
    image_filename = "%s-ccuts-%s.svg" % (output_path, lower)
    drawing = svgwrite.Drawing(
        image_filename, size=(terrain.shape[1], terrain.shape[0]), profile="tiny"
    )
    # Contours
    for contour in contours:
        simplified_contour = simplification.cutil.simplify_coords_vw(
            [(x, y) for (y, x) in contour], simp
        )
        drawing.add(
            drawing.polyline(points=simplified_contour, stroke="blue", fill="none")
        )
    # Border
    drawing.add(
        drawing.rect(
            (0, 0), (terrain.shape[1], terrain.shape[0]), stroke="blue", fill="none"
        )
    )
    drawing.save()
    click.echo("  Saved cut SVG %s" % image_filename)

    # Return terrain mask
    return terrain


def make_image(arr, terrains, lower, upper, image, output_path, bleed):
    """
    Calculates the image for one contour range.
    """
    # Turn the array into a bitmap of "is it in range" for the image calculation,
    # based on the already-smoothed terrains
    mask = numpy.copy(terrains[lower])
    if upper in terrains:
        for y in range(mask.shape[0]):
            for x in range(mask.shape[1]):
                if terrains[upper][y, x]:
                    mask[y, x] = 0
    # Bleed that boundary out
    for i in range(bleed):
        new_mask = numpy.copy(mask)
        # Go through each pixel and mark it as True if any of its immediate
        # neighbours are True
        for y in range(mask.shape[0]):
            for x in range(mask.shape[1]):
                pixel = mask[y, x]
                if any(
                    mask[y + dy, x + dx]
                    for dx, dy in [
                        (-1, -1),
                        (0, -1),
                        (1, -1),
                        (-1, 0),
                        (1, 0),
                        (-1, 1),
                        (0, 1),
                        (1, 1),
                    ]
                    if (0 <= y + dy < mask.shape[0] and 0 <= x + dx < mask.shape[1])
                ):
                    new_mask[y, x] = True
        mask = new_mask
    # Turn that into an actual image object (add a border for alignment later)
    mask_image = bitmap_array_to_image(mask)
    draw_border(mask_image, colour=1)
    # Scale it to match the original image size
    mask_image = mask_image.resize(image.size)
    # Create an all-transparent base image
    base_image = PIL.Image.new("RGBA", image.size, color=(0, 0, 0, 0))
    # Mask them together
    new_image = PIL.Image.composite(image, base_image, mask_image)
    # Save output
    image_filename = "%s-cimage-%s.png" % (output_path, lower)
    new_image.save(image_filename)
    click.echo("  Saved image %s" % image_filename)
