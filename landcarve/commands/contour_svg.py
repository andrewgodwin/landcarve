import click
import numpy
import simplification.cutil
import skimage.measure
import skimage.morphology
import svgwrite

from landcarve.cli import main
from landcarve.utils.io import raster_to_array


@main.command()
@click.option(
    "--simp",
    default=0.5,
    type=float,
    help="Visvalingam-Whyatt simplification coefficient (0 to skip)",
)
@click.option(
    "--tension",
    default=1.0,
    type=float,
    help="Catmull-Rom tension for smoothing (higher = tighter curves)",
)
@click.option(
    "--min-object",
    default=0.5,
    type=float,
    help="Remove above-level regions smaller than this percentage of total pixels",
)
@click.option(
    "--min-hole",
    default=0.5,
    type=float,
    help="Fill holes in above-level regions smaller than this percentage of total pixels",
)
@click.option(
    "--min-points",
    default=4,
    type=int,
    help="Minimum number of points a contour must have to be included",
)
@click.option(
    "--stroke-width",
    default=1.0,
    type=float,
    help="SVG stroke width",
)
@click.option(
    "--stroke-color",
    default="black",
    type=str,
    help="SVG stroke color",
)
@click.argument("input_path")
@click.argument("output_path")
@click.argument("height", type=float)
def contour_svg(
    input_path,
    output_path,
    height,
    simp,
    tension,
    min_object,
    min_hole,
    min_points,
    stroke_width,
    stroke_color,
):
    """
    Extracts a single contour line at a given HEIGHT from a geo raster image
    and outputs it as a smoothed SVG path using cubic Bezier curves.

    Contours that reach the image boundary are closed by tracing along the
    edge where values are above HEIGHT. Open fragments belonging to the same
    region are joined automatically. Boundary segments are kept as straight
    lines; only interior segments are smoothed.
    """
    arr = raster_to_array(input_path)
    h, w = arr.shape

    # Build a binary mask of pixels at or above the level, then pad with zeros
    # so that every above-level region is surrounded by below-level values.
    # find_contours on the padded mask produces only closed contours; those that
    # originally hit the image edge are closed along boundary pixels >= height,
    # and open fragments of the same region are joined automatically.
    total_pixels = h * w
    mask = arr >= height
    mask = skimage.morphology.remove_small_holes(
        mask, area_threshold=int(total_pixels * min_hole / 100)
    )
    mask = skimage.morphology.remove_small_objects(
        mask, min_size=int(total_pixels * min_object / 100)
    )

    # Apply the cleaned mask back to the float array so removed regions are
    # definitively below the level, then pad with the same sentinel value.
    # Running find_contours on the float array (rather than the binary mask)
    # gives sub-pixel interpolated positions — no pixel-boundary staircase.
    pad_value = height - 1
    cleaned = numpy.where(mask, arr, pad_value)
    padded = numpy.pad(cleaned, 1, mode="constant", constant_values=pad_value)
    raw_contours = skimage.measure.find_contours(padded, height)
    click.echo(f"Found {len(raw_contours)} contour(s) at height {height}")

    contours = []
    for contour in raw_contours:
        # Shift back from padded coordinates and clamp to the original image bounds
        contour = contour - 1.0
        contour[:, 0] = numpy.clip(contour[:, 0], 0.0, h - 1.0)
        contour[:, 1] = numpy.clip(contour[:, 1], 0.0, w - 1.0)

        # Strip the closing duplicate that skimage appends for closed contours
        if len(contour) > 1 and numpy.linalg.norm(contour[0] - contour[-1]) < 0.01:
            contour = contour[:-1]

        if simp > 0:
            contour = numpy.array(
                simplification.cutil.simplify_coords_vw(contour, simp)
            )

        if len(contour) >= min_points:
            contours.append(contour)

    click.echo(f"Kept {len(contours)} contour(s) after simplification")

    drawing = svgwrite.Drawing(output_path, size=(w, h), profile="full")
    for contour in contours:
        points = contour[:, [1, 0]]  # (row, col) → (x, y)
        # Tag points on the image boundary — these must stay sharp
        on_edge = _on_image_edge(points, w, h)
        path_d = _catmull_rom_path(points, on_edge, tension=tension)
        drawing.add(
            drawing.path(
                d=path_d,
                stroke=stroke_color,
                fill="none",
                stroke_width=stroke_width,
            )
        )

    drawing.save()
    click.echo(f"Saved to {output_path}")


_EDGE_TOL = 0.01


def _on_image_edge(points, w, h):
    """Returns a boolean array: True where a point lies on the image boundary."""
    x, y = points[:, 0], points[:, 1]
    return (
        (x < _EDGE_TOL)
        | (x > w - 1 - _EDGE_TOL)
        | (y < _EDGE_TOL)
        | (y > h - 1 - _EDGE_TOL)
    )


def _catmull_rom_path(points, on_edge, tension=1.0):
    """
    Converts a closed sequence of (x, y) points into an SVG path string.

    Interior segments (both endpoints off the image edge) are smoothed with
    Catmull-Rom cubic Bezier curves. Segments where either endpoint is on the
    image edge use straight L commands, preserving sharp corners. At the
    transition between edge and interior the Catmull-Rom tangent is suppressed
    so the curve departs cleanly from the boundary without being pulled along it.
    """
    pts = numpy.array(points, dtype=float)
    n = len(pts)

    # Wrap for closed contour
    ext = numpy.vstack([pts[-1:], pts, pts[:2]])
    bnd = numpy.concatenate([[on_edge[-1]], on_edge, on_edge[:2]])

    path = f"M {ext[1][0]:.3f},{ext[1][1]:.3f}"

    for i in range(n):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        b1 = bnd[i + 1]  # is the source (p1) on the edge?
        b2 = bnd[i + 2]  # is the destination (p2) on the edge?

        if b1 or b2:
            path += f" L {p2[0]:.3f},{p2[1]:.3f}"
        else:
            # Suppress the tangent contribution from any boundary neighbour so
            # the curve departs cleanly from the edge instead of being pulled
            # back along it.
            p_eff0 = p1 if bnd[i] else p0
            p_eff3 = p2 if bnd[i + 3] else p3
            cp1 = p1 + (p2 - p_eff0) * tension / 6.0
            cp2 = p2 - (p_eff3 - p1) * tension / 6.0
            path += (
                f" C {cp1[0]:.3f},{cp1[1]:.3f}"
                f" {cp2[0]:.3f},{cp2[1]:.3f}"
                f" {p2[0]:.3f},{p2[1]:.3f}"
            )

    path += " Z"
    return path
