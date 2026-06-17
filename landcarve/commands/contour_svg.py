import click
import numpy
import scipy.ndimage
import simplification.cutil
import skimage.measure
import skimage.morphology
import svgwrite

from landcarve.cli import main
from landcarve.utils.io import raster_to_array


def _float_arg(value):
    """
    Parse a float, tolerating Unicode minus/dash characters (e.g. U+2212)
    that commonly slip in when copy-pasting elevations from QGIS, PDFs or
    web pages, where they would otherwise fail plain float() parsing.
    """
    normalized = (
        value.replace("−", "-")  # minus sign
        .replace("‒", "-")  # figure dash
        .replace("–", "-")  # en dash
        .replace("—", "-")  # em dash
    )
    try:
        return float(normalized)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a valid floating point value")


@main.command(context_settings={"ignore_unknown_options": True})
@click.option(
    "--simp",
    default=0.2,
    type=float,
    help="Visvalingam-Whyatt simplification coefficient (0 to skip)",
)
@click.option(
    "--smooth",
    default=0.0,
    type=float,
    help="Gaussian smoothing sigma in pixels applied along each contour to "
    "remove the pixel-grid staircase (0 to skip)",
)
@click.option(
    "--tension",
    default=3.0,
    type=float,
    help="Catmull-Rom tension for smoothing (higher = tighter curves)",
)
@click.option(
    "--min-object",
    default=0.2,
    type=float,
    help="Remove above-level regions smaller than this percentage of total pixels",
)
@click.option(
    "--min-hole",
    default=0.1,
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
@click.option(
    "--fill-color",
    default="none",
    type=str,
    help="SVG fill color",
)
@click.argument("input_path")
@click.argument("output_path")
@click.argument("height", type=_float_arg)
def contour_svg(
    input_path,
    output_path,
    height,
    simp,
    smooth,
    tension,
    min_object,
    min_hole,
    min_points,
    stroke_width,
    stroke_color,
    fill_color,
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
        mask, max_size=int(total_pixels * min_hole / 100)
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

        # Low-pass the (still dense) contour to wash out the pixel-grid
        # staircase before simplification picks vertices. Boundary points are
        # held fixed so contours closed along the image edge stay sharp.
        if smooth > 0:
            on_edge = _on_image_edge(contour[:, [1, 0]], w, h)
            contour = _smooth_contour(contour, on_edge, smooth)

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
                fill=fill_color,
                stroke_width=stroke_width,
            )
        )

    drawing.save()
    click.echo(f"Saved to {output_path}")


_EDGE_TOL = 0.01


def _smooth_contour(contour, on_edge, sigma):
    """
    Gaussian-smooths a closed contour's coordinates to remove the pixel-grid
    staircase, returning a new array of the same length.

    Fully interior contours are smoothed as a periodic loop (mode="wrap").
    Contours that touch the image boundary are smoothed run-by-run between the
    boundary points, which are kept exactly in place; each run uses its
    bracketing boundary point(s) as fixed context so the smoothed curve stays
    continuous with the straight edge segments.
    """
    n = len(contour)
    if n < 3:
        return contour

    if not on_edge.any():
        out = contour.copy()
        out[:, 0] = scipy.ndimage.gaussian_filter1d(contour[:, 0], sigma, mode="wrap")
        out[:, 1] = scipy.ndimage.gaussian_filter1d(contour[:, 1], sigma, mode="wrap")
        return out

    # Rotate so the sequence starts on a boundary point; this prevents an
    # interior run from being split across the array's wrap-around seam.
    shift = int(numpy.argmax(on_edge))
    rolled = numpy.roll(contour, -shift, axis=0)
    rolled_edge = numpy.roll(on_edge, -shift)

    out = rolled.copy()
    i = 0
    while i < n:
        if rolled_edge[i]:
            i += 1
            continue
        j = i
        while j < n and not rolled_edge[j]:
            j += 1
        # Interior run [i, j); include the bracketing boundary anchors (which
        # always exist here, since the run is delimited by edge points) so the
        # smoothing near the run's ends is pulled toward the boundary. The
        # trailing anchor wraps to index 0 when the run reaches the array end.
        right = j if j < n else 0
        seg_idx = [i - 1] + list(range(i, j)) + [right]
        seg = rolled[seg_idx]
        sm = seg.copy()
        sm[:, 0] = scipy.ndimage.gaussian_filter1d(seg[:, 0], sigma, mode="nearest")
        sm[:, 1] = scipy.ndimage.gaussian_filter1d(seg[:, 1], sigma, mode="nearest")
        out[i:j] = sm[1:-1]  # write back the interior only; anchors stay fixed
        i = j

    return numpy.roll(out, shift, axis=0)


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
