import re

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
    "--scale",
    default=1.0,
    type=float,
    help="Scale factor applied to raster coordinates to produce final SVG coords",
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
@click.option(
    "--dxf/--no-dxf",
    "dxf",
    default=True,
    help="Also write a DXF (in mm) alongside the SVG for laser-cutter import",
)
@click.option(
    "--dxf-samples",
    default=12,
    type=int,
    help="Points sampled per curved segment when flattening to DXF polylines",
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
    scale,
    stroke_width,
    stroke_color,
    fill_color,
    dxf,
    dxf_samples,
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

    drawing = svgwrite.Drawing(
        output_path, size=(w * scale, h * scale), profile="full"
    )
    dxf_polylines = []
    total_height = h * scale  # for flipping Y into CAD orientation (Y up)
    for contour in contours:
        points = contour[:, [1, 0]]  # (row, col) → (x, y)
        # Tag points on the image boundary (in pixel coords) — these must stay sharp
        on_edge = _on_image_edge(points, w, h)
        # Scale pixel coordinates into the final SVG coordinate space
        points = points * scale
        start, segments = _catmull_rom_segments(points, on_edge, tension=tension)
        path_d = _catmull_rom_path(points, on_edge, tension=tension)
        drawing.add(
            drawing.path(
                d=path_d,
                stroke=stroke_color,
                fill=fill_color,
                stroke_width=stroke_width,
            )
        )
        if dxf:
            flat = _flatten_segments(start, segments, dxf_samples)
            # Flip Y so the contour imports right-side-up in CAD/laser software.
            flat[:, 1] = total_height - flat[:, 1]
            dxf_polylines.append(flat)

    drawing.save()
    click.echo(f"Saved to {output_path}")

    if dxf:
        dxf_path = re.sub(r"\.[^.]+$", "", output_path) + ".dxf"
        _write_dxf(dxf_path, dxf_polylines)
        click.echo(f"Saved DXF (mm) to {dxf_path}")


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


def _catmull_rom_segments(points, on_edge, tension=1.0):
    """
    Converts a closed sequence of (x, y) points into Bezier path segments.

    Returns (start, segments) where start is the first (x, y) point and each
    segment is either ("line", p2) or ("curve", cp1, cp2, p2). This is the
    shared geometry used to render both the SVG path and the flattened DXF
    polyline.

    Interior segments (both endpoints off the image edge) are smoothed with
    Catmull-Rom cubic Bezier curves. Segments where either endpoint is on the
    image edge stay straight, preserving sharp corners. At the transition
    between edge and interior the Catmull-Rom tangent is suppressed so the curve
    departs cleanly from the boundary without being pulled along it.
    """
    pts = numpy.array(points, dtype=float)
    n = len(pts)

    # Wrap for closed contour
    ext = numpy.vstack([pts[-1:], pts, pts[:2]])
    bnd = numpy.concatenate([[on_edge[-1]], on_edge, on_edge[:2]])

    segments = []
    for i in range(n):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        b1 = bnd[i + 1]  # is the source (p1) on the edge?
        b2 = bnd[i + 2]  # is the destination (p2) on the edge?

        if b1 or b2:
            segments.append(("line", p2))
        else:
            # Suppress the tangent contribution from any boundary neighbour so
            # the curve departs cleanly from the edge instead of being pulled
            # back along it.
            p_eff0 = p1 if bnd[i] else p0
            p_eff3 = p2 if bnd[i + 3] else p3
            cp1 = p1 + (p2 - p_eff0) * tension / 6.0
            cp2 = p2 - (p_eff3 - p1) * tension / 6.0
            segments.append(("curve", cp1, cp2, p2))

    return ext[1], segments


def _catmull_rom_path(points, on_edge, tension=1.0):
    """Builds a closed SVG path string from the Catmull-Rom segments."""
    start, segments = _catmull_rom_segments(points, on_edge, tension)
    path = f"M {start[0]:.3f},{start[1]:.3f}"
    for seg in segments:
        if seg[0] == "line":
            p2 = seg[1]
            path += f" L {p2[0]:.3f},{p2[1]:.3f}"
        else:
            _, cp1, cp2, p2 = seg
            path += (
                f" C {cp1[0]:.3f},{cp1[1]:.3f}"
                f" {cp2[0]:.3f},{cp2[1]:.3f}"
                f" {p2[0]:.3f},{p2[1]:.3f}"
            )
    path += " Z"
    return path


def _flatten_segments(start, segments, samples):
    """
    Flattens Catmull-Rom path segments into a dense list of (x, y) points.

    Straight segments contribute their endpoint; curve segments are sampled at
    `samples` points along the cubic Bezier. The result is a closed polyline
    (the final point coincides with `start`) suitable for a DXF polyline.
    """
    out = [numpy.asarray(start, dtype=float)]
    for seg in segments:
        if seg[0] == "line":
            out.append(numpy.asarray(seg[1], dtype=float))
        else:
            _, cp1, cp2, p2 = seg
            p1 = out[-1]
            for k in range(1, samples + 1):
                t = k / samples
                mt = 1.0 - t
                pt = (
                    mt**3 * p1
                    + 3 * mt**2 * t * cp1
                    + 3 * mt * t**2 * cp2
                    + t**3 * p2
                )
                out.append(pt)
    return numpy.array(out)


def _write_dxf(output_path, polylines):
    """
    Writes closed polylines to an ASCII DXF (R12) file in millimetres.

    Each polyline is a sequence of (x, y) points (CAD orientation, Y up). R12
    POLYLINE entities are used for maximum compatibility with laser-cutter
    software; $INSUNITS=4 declares the drawing units as millimetres.
    """
    lines = [
        "0", "SECTION",
        "2", "HEADER",
        "9", "$ACADVER", "1", "AC1009",
        "9", "$INSUNITS", "70", "4",
        "0", "ENDSEC",
        "0", "SECTION",
        "2", "ENTITIES",
    ]
    for poly in polylines:
        lines += [
            "0", "POLYLINE",
            "8", "0",
            "66", "1",
            "70", "1",  # closed polyline
        ]
        for x, y in poly:
            lines += [
                "0", "VERTEX",
                "8", "0",
                "10", f"{x:.4f}",
                "20", f"{y:.4f}",
            ]
        lines += ["0", "SEQEND"]
    lines += ["0", "ENDSEC", "0", "EOF"]

    with open(output_path, "w") as fp:
        fp.write("\n".join(lines) + "\n")
