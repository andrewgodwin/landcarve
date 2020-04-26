import os
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
from landcarve.utils.graphics import (
    bitmap_array_to_image,
    draw_border,
    draw_crosshatch,
    draw_contours,
    draw_labels,
)


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
@click.option(
    "--line-scale",
    default=2,
    type=int,
    help="Scaling factor for graphical elements in the output",
)
@click.option(
    "--page-size",
    default=None,
    type=str,
    help="Page size in pixels for the output, if different to the input image size",
)
@click.argument("input_path")
@click.argument("output_path")
@click.argument("image_path")
@click.argument("contours")
def contour_image(
    input_path,
    output_path,
    image_path,
    contours,
    bleed,
    min_object,
    min_hole,
    simp,
    line_scale,
    page_size,
):
    """
    Slices a terrain into contour segments and then outputs an image and a cut
    line for each of the segments.

    If used in a pipeline, must be the final item as it uses the output path
    as a prefix.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)

    # Load the original map details image using Pillow
    image = PIL.Image.open(image_path).convert(mode="RGBA")

    # Check output path
    if not os.path.isdir(output_path):
        click.error("Output path must be a directory")
        return 1

    # Check contour list
    contour_list = sorted(
        [int(x) if int(x) == float(x) else float(x) for x in contours.split(",")]
    )
    contour_list.append(99999999999)
    if len(contour_list) < 3:
        raise ValueError("You must pass at least 2 contour boundaries")

    # Process any page size string
    if page_size:
        page_size = [int(x) for x in page_size.replace(",", "x").split("x")]
        assert len(page_size) == 2

    processor = ContourProcessor(
        arr,
        image,
        {
            "minimum_object": min_object,
            "minimum_hole": min_hole,
            "bleed": bleed,
            "contour_simplification": simp,
            "line_scale": line_scale,
        },
    )
    processor.cut_contours(contour_list, output_path, page_size=page_size)


class ContourProcessor:
    """
    Takes a heightmap and an image, and outputs images that allow construction
    of the resulting landscape as contour pieces.
    """

    def __init__(self, base_terrain, detail_image, options=None):
        self.base_terrain = base_terrain
        self.detail_image = detail_image

        # Retrieve options
        self.options = options or {}
        self.bleed = int(options.get("bleed", 2))
        self.contour_simplification = float(options.get("contour_simplification", 0.5))
        self.minimum_hole = float(options.get("minimum_hole", 0.02))
        self.minimum_object = float(options.get("minimum_object", 0.05))
        self.line_scale = int(options.get("line_scale", 2))

        # Generate the fill image for "land above"
        self.above_image = PIL.Image.new(
            "RGBA", self.detail_image.size, color=(0, 0, 0, 0)
        )
        draw_crosshatch(
            self.above_image,
            step=15 * self.line_scale,
            width=int(self.line_scale / 2) or 1,
        )

    def cut_contours(self, contours, output_path, page_size):
        # Slice the terrain by contours
        self.terrains = {}
        click.echo("Slicing terrain...")
        for lower, upper in zip(contours, contours[1:]):
            self.terrains[lower] = self.slice_terrain(lower, upper)

        # Generate construction images for each contour
        click.echo("Generating construction images...")
        for lower, upper in zip(contours, contours[1:]):
            click.echo("  Contour %s" % lower)
            construction_image = self.make_construction_image(lower, upper)
            construction_image.save(
                os.path.join(output_path, "contour_%s_construction.png" % lower)
            )

        # For each terrain, calculate each possible component and generate
        # image snippets
        click.echo("Extracting pieces...")
        pieces = []
        for lower, upper in zip(contours, contours[1:]):
            click.echo("  Contour %s" % lower)
            for piece in self.make_terrain_pieces(lower, upper):
                # piece["image"].save(
                #     os.path.join(output_path, "piece_%s.png" % piece["label"])
                # )
                pieces.append(piece)

        # Lay out the pieces on pages
        click.echo("Laying out pages...")
        for i, page in enumerate(
            self.layout_pages(pieces, page_size or self.detail_image.size), 1
        ):
            # Save image
            page.image.save(os.path.join(output_path, "page_%03i_image.png" % i))
            # Save contours
            self.contours_to_svg(
                page.contours,
                page.image.size,
                os.path.join(output_path, "page_%03i_contours.svg" % i),
            )
            # Save mapping image
            self.make_guide_image(page).save(
                os.path.join(output_path, "page_%03i_guide.png" % i)
            )
            click.echo("  Saved page %i" % i)

    def slice_terrain(self, lower, upper):
        """
        Slices a bitmap of "at or above this level" out of the terrain and removes
        small holes or objects.
        """
        # Bitmap based on height
        terrain = numpy.vectorize(lambda x: lower <= x, otypes="?")(self.base_terrain)

        # Fill small holes
        hole_threshold = int(
            terrain.shape[0] * terrain.shape[1] * 0.01 * self.minimum_hole
        )
        object_threshold = int(
            terrain.shape[0] * terrain.shape[1] * 0.01 * self.minimum_object
        )
        terrain = skimage.morphology.remove_small_holes(
            terrain, area_threshold=hole_threshold, in_place=True
        )
        terrain = skimage.morphology.remove_small_objects(
            terrain, min_size=object_threshold, in_place=True
        )
        return terrain

    def make_construction_image(self, lower, upper):
        """
        Makes a "print image" of this contour - detail for land below or in
        range, and above_image where there's land above, with cut marks traced.
        """
        # Turn the current terrain into a bitmap mask
        mask_image = bitmap_array_to_image(self.terrains[lower]).resize(
            self.detail_image.size
        )
        # Create a semi-transparent base image
        image = PIL.Image.new(
            "RGBA", self.detail_image.size, color=(255, 255, 255, 255)
        )
        image = PIL.Image.blend(image, self.detail_image, 0.5)
        # Layer on the detail
        image = PIL.Image.composite(self.detail_image, image, mask_image)
        # Make an image pattern to represent "terrain above" and mask it in if needed
        if upper in self.terrains:
            above_mask_image = bitmap_array_to_image(self.terrains[upper]).resize(
                self.detail_image.size
            )
            image = PIL.Image.composite(self.above_image, image, above_mask_image)
        # Draw on contours
        contours = self.convert_and_simplify_contours(
            skimage.measure.find_contours(self.terrains[lower], 0.5),
            x_scale=image.size[0] / self.base_terrain.shape[1],
            y_scale=image.size[1] / self.base_terrain.shape[0],
        )
        draw_contours(image, contours, width=self.line_scale)
        return image

    def make_terrain_pieces(self, lower, upper):
        """
        Takes a contour and slices out the pieces, saving them individually for
        later reconstruction into printable pages.
        """
        # Label the pieces of the contour
        labelled_terrain, num_labels = skimage.measure.label(
            self.terrains[lower], return_num=True, connectivity=2
        )
        # Make an image to cut out pieces from with overhead hatched out
        empty_image = PIL.Image.new("RGBA", self.detail_image.size, color=(0, 0, 0, 0))
        full_image = self.detail_image.copy()
        if upper in self.terrains:
            above_mask_image = bitmap_array_to_image(
                skimage.morphology.erosion(
                    self.terrains[upper],
                    selem=skimage.morphology.square((self.bleed * 2) + 1),
                )
            ).resize(full_image.size)
            full_image = PIL.Image.composite(
                self.above_image, full_image, above_mask_image
            )
        # For each piece, extract
        for i in range(1, num_labels + 1):
            # Create a mask array that is just this piece, cutting around the border to force contours
            piece_mask = numpy.vectorize(lambda x: x == i, otypes="?")(labelled_terrain)
            for x in range(0, piece_mask.shape[1]):
                for y in (0, piece_mask.shape[0] - 1):
                    piece_mask[y, x] = 0
            for y in range(0, piece_mask.shape[0]):
                for x in (0, piece_mask.shape[1] - 1):
                    piece_mask[y, x] = 0
            # Bleed the mask out a bit to make a print mask
            bleed_mask = skimage.morphology.dilation(
                piece_mask, selem=skimage.morphology.square((self.bleed * 2) + 1)
            )
            # Resize both masks up into images
            piece_mask_image = bitmap_array_to_image(piece_mask).resize(full_image.size)
            bleed_mask_image = bitmap_array_to_image(bleed_mask).resize(full_image.size)
            # Composite from the detail image using the bleed mask
            piece_image = PIL.Image.composite(full_image, empty_image, bleed_mask_image)
            # Trace the piece's contours
            contours = self.convert_and_simplify_contours(
                skimage.measure.find_contours(piece_mask, 0.5),
                x_scale=full_image.size[0] / piece_mask.shape[1],
                y_scale=full_image.size[1] / piece_mask.shape[0],
            )
            # Work out bounds of the piece we have and cut out the cropped version
            bounds = piece_image.getbbox()
            cut_image = piece_image.crop(bounds)
            # Shift the contours to match
            contours = [
                [(x - bounds[0], y - bounds[1]) for x, y in contour]
                for contour in contours
            ]
            # Yield piece
            yield Piece(layer="c%s" % lower, image=cut_image, contours=contours)

    def convert_and_simplify_contours(self, contours, x_scale=1, y_scale=1):
        """
        Takes an Array of contours in (y, x) format, simplifies them, and returns
        as a generator of lists of (x, y) format. Optionally does scaling too.
        """
        for contour in contours:
            yield [
                ((x_scale / 2) + x * x_scale, (y_scale / 2) + y * y_scale)
                for y, x in simplification.cutil.simplify_coords_vw(
                    contour, self.contour_simplification
                )
            ]

    def layout_pages(self, pieces, page_size):
        """
        Takes the list of pieces and lays them out onto as few printable pages
        as possible.
        """
        # First, order the pieces by size
        pieces.sort(key=lambda p: p.magnitude, reverse=True)
        pages = []
        # Go through each piece and put it on the first page it fits on
        for i, piece in enumerate(pieces):
            if i % 5 == 0:
                print("  Piece %i" % i)
            # See if it fits on any existing pages
            for page in pages:
                offset = page.can_place(piece)
                if offset is not None:
                    page.add_piece(piece, offset)
                    break
            else:
                page = Page(page_size)
                page.add_piece(piece, (0, 0))
                pages.append(page)
        return pages

    def make_guide_image(self, page):
        """
        Makes a version of the page image that shows what layers each piece
        belongs to.
        """
        # Dim main image
        image = PIL.Image.new("RGBA", page.image.size, color=(255, 255, 255, 255))
        image = PIL.Image.blend(image, page.image, 0.9)
        # Draw on contours
        draw_contours(image, page.contours, width=self.line_scale)
        # Draw on labels
        draw_labels(image, page.labels, size=10 * self.line_scale)
        return image

    def contours_to_svg(self, contours, size, filename):
        """
        Saves a set of contours as an SVG file
        """
        drawing = svgwrite.Drawing(filename, size=(size[0], size[1]), profile="tiny")
        # Contours
        for contour in contours:
            drawing.add(drawing.polyline(points=contour, stroke="black", fill="none"))
        # Border
        drawing.add(
            drawing.rect((0, 0), (size[0], size[1]), stroke="blue", fill="none")
        )
        drawing.save()


class Piece:
    """
    Represents a single piece that needs printing
    """

    def __init__(self, layer, image, contours):
        self.layer = layer
        self.image = image
        self.size = self.image.size
        self.magnitude = self.size[0] * self.size[1]
        self.contours = contours


class Page:
    """
    Represents a single page containing one or more pieces to print
    """

    def __init__(self, size):
        self.size = size
        self.image = PIL.Image.new("RGBA", self.size, color=(0, 0, 0, 0))
        self.contours = []
        self.labels = []
        # Add a 1px border to the image for alignment
        for x in range(0, self.size[0]):
            for y in (0, self.size[1] - 1):
                self.image.putpixel((x, y), (0, 0, 0, 255))
        for x in (0, self.size[0] - 1):
            for y in range(0, self.size[1]):
                self.image.putpixel((x, y), (0, 0, 0, 255))

    def add_piece(self, piece, offset):
        self.image.alpha_composite(piece.image, dest=offset)
        for contour in piece.contours:
            self.contours.append([(x + offset[0], y + offset[1]) for x, y in contour])
            self.labels.append((piece.layer, self.contours[-1][0]))

    def can_place(self, piece):
        """
        Works out if the given piece will fit on the page. Returns None if not,
        or the offset it can have if it will.
        """
        for y in range(0, self.size[1], 100):
            for x in range(0, self.size[0], 100):
                if self.can_place_at(piece, (x, y)):
                    return (x, y)
        return None

    def can_place_at(self, piece, offset):
        # Check dimensions
        if (offset[0] + piece.size[0] > self.size[0]) or (
            offset[1] + piece.size[1] > self.size[1]
        ):
            return False
        # Initial quick pass
        for dx in range(0, piece.size[0], int(piece.size[0] / 10)):
            for dy in range(0, piece.size[1], int(piece.size[1] / 10)):
                if piece.image.getpixel((dx, dy))[3]:
                    if self.image.getpixel((offset[0] + dx, offset[1] + dy))[3]:
                        return False
        # Full pass
        for dx in range(0, piece.size[0]):
            for dy in range(0, piece.size[1]):
                if piece.image.getpixel((dx, dy))[3]:
                    if self.image.getpixel((offset[0] + dx, offset[1] + dy))[3]:
                        return False
        return True
