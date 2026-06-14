import math
import re
import xml.etree.ElementTree as ET

import click
import numpy
import scipy.signal
import skimage.draw
import scipy.ndimage
import svgwrite

from landcarve.cli import main


@main.command()
@click.option(
    "--resolution",
    default=1.0,
    type=float,
    help="Mask pixels per SVG unit used for packing (higher = tighter but slower)",
)
@click.option(
    "--margin",
    default=2.0,
    type=float,
    help="Minimum gap to leave between pieces, in SVG units",
)
@click.option(
    "--rotations",
    default=4,
    type=int,
    help="Number of discrete rotations to try per piece (1 = keep original orientation)",
)
@click.option(
    "--width",
    default=0.0,
    type=float,
    help="Width of the output sheet in SVG units (0 = pick an approximately square sheet)",
)
@click.option(
    "--curve-steps",
    default=12,
    type=int,
    help="Segments used to flatten Bezier curves when rasterising for packing",
)
@click.argument("input_paths", nargs=-1, required=True)
@click.argument("output_path")
def pack_svg(
    input_paths,
    output_path,
    resolution,
    margin,
    rotations,
    width,
    curve_steps,
):
    """
    Packs several contour SVGs (as produced by contour-svg) into a single SVG,
    nesting the pieces with as little space between them as possible.

    Each input file is treated as one rigid piece: all of its paths are kept
    together and moved/rotated as a unit. Pieces are rasterised into bitmaps so
    that concave shapes (and holes) can nest into one another, then placed with a
    greedy bottom-left fill. The original Bezier path data is preserved exactly in
    the output; only a group transform is applied to each piece.
    """
    res = resolution
    margin_px = max(0, int(round(margin * res)))

    # Load every input file into a piece: its raw <path> elements (for output)
    # plus flattened polylines (for rasterising / measuring).
    pieces = []
    for path in input_paths:
        paths, polylines = _load_svg(path, curve_steps)
        if not polylines:
            click.echo(f"Skipping {path}: no drawable paths found", err=True)
            continue
        pieces.append({"name": path, "paths": paths, "polylines": polylines})

    if not pieces:
        raise click.ClickException("No usable pieces found in the input files")

    click.echo(f"Loaded {len(pieces)} piece(s)")

    # Build the candidate rotations (in degrees).
    rotations = max(1, rotations)
    angles = [i * 360.0 / rotations for i in range(rotations)]

    # For every piece work out its mask under each rotation, along with the
    # rotated bounding-box minimum that the output transform needs.
    for piece in pieces:
        variants = []
        for deg in angles:
            rotated = [_rotate(pl, deg) for pl in piece["polylines"]]
            all_pts = numpy.vstack(rotated)
            rmin = all_pts.min(axis=0)
            mask = _rasterise(rotated, rmin, res)
            # Dilate by the margin so packing leaves a gap around each piece.
            if margin_px > 0:
                mask = numpy.pad(mask, margin_px, mode="constant")
                mask = scipy.ndimage.binary_dilation(mask, iterations=margin_px)
            variants.append({"deg": deg, "rmin": rmin, "mask": mask})
        piece["variants"] = variants
        piece["area"] = max(int(v["mask"].sum()) for v in variants)

    # Place the biggest pieces first.
    pieces.sort(key=lambda p: p["area"], reverse=True)

    # Decide the sheet width in pixels. Default to an approximately square sheet
    # based on the total bounding-box area of all pieces.
    if width > 0:
        bin_w = int(round(width * res))
    else:
        total_bbox = sum(
            min(v["mask"].shape[0] for v in p["variants"])
            * min(v["mask"].shape[1] for v in p["variants"])
            for p in pieces
        )
        bin_w = int(round(math.sqrt(total_bbox) * 1.1))
    # The sheet must be at least as wide as the widest piece.
    widest = max(v["mask"].shape[1] for p in pieces for v in p["variants"])
    bin_w = max(bin_w, widest)

    # The occupancy canvas grows downwards as needed.
    canvas = numpy.zeros((max(bin_w, 1), bin_w), dtype=bool)

    placements = []
    for index, piece in enumerate(pieces, 1):
        placement = _place(canvas, piece["variants"])
        # Grow the canvas until the piece fits.
        while placement is None:
            tallest = max(v["mask"].shape[0] for v in piece["variants"])
            extra = numpy.zeros((max(tallest, bin_w // 4), bin_w), dtype=bool)
            canvas = numpy.vstack([canvas, extra])
            placement = _place(canvas, piece["variants"])

        variant, x, y = placement
        mask = variant["mask"]
        rows, cols = numpy.nonzero(mask)
        canvas[y + rows, x + cols] = True

        # Convert the placement back into an SVG transform. The piece's rotated
        # bounding-box minimum currently sits at pixel (margin_px, margin_px)
        # inside its (padded + dilated) mask.
        world_x = (x + margin_px) / res
        world_y = (y + margin_px) / res
        tx = world_x - variant["rmin"][0]
        ty = world_y - variant["rmin"][1]
        placements.append(
            {"piece": piece, "deg": variant["deg"], "tx": tx, "ty": ty}
        )
        click.echo(f"Placed {index}/{len(pieces)}: {piece['name']}")

    # Final used extent.
    used = numpy.nonzero(canvas)
    used_h = (used[0].max() + 1) if len(used[0]) else 1
    used_w = (used[1].max() + 1) if len(used[1]) else bin_w
    sheet_w = used_w / res
    sheet_h = used_h / res

    # Write the combined SVG, one transformed group per piece.
    drawing = svgwrite.Drawing(
        output_path, size=(sheet_w, sheet_h), profile="full"
    )
    for placement in placements:
        transform = f"translate({placement['tx']:.3f},{placement['ty']:.3f})"
        if placement["deg"]:
            transform += f" rotate({placement['deg']:.3f})"
        group = drawing.g(transform=transform)
        for path in placement["piece"]["paths"]:
            group.add(drawing.path(d=path["d"], **path["attrs"]))
        drawing.add(group)
    drawing.save()

    click.echo(
        f"Packed {len(placements)} piece(s) into "
        f"{sheet_w:.1f} x {sheet_h:.1f} -> {output_path}"
    )


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def _place(canvas, variants):
    """
    Finds the lowest (then left-most) collision-free position for any rotation
    variant of a piece on the canvas. Returns (variant, x, y) or None if nothing
    fits within the current canvas height.
    """
    best = None
    for variant in variants:
        mask = variant["mask"]
        mh, mw = mask.shape
        if mh > canvas.shape[0] or mw > canvas.shape[1]:
            continue
        # Correlate the mask against the occupancy map; a zero means no overlap.
        overlap = scipy.signal.fftconvolve(
            canvas.astype(numpy.float32), mask[::-1, ::-1].astype(numpy.float32),
            mode="valid",
        )
        free = overlap < 0.5
        rows = numpy.where(free.any(axis=1))[0]
        rmask, cmask = numpy.nonzero(mask)
        for y in rows:
            if best is not None and y > best[2]:
                break
            for x in numpy.where(free[y])[0]:
                if best is not None and (y, x) >= (best[2], best[1]):
                    break
                # FFT rounding can lie; verify exactly before trusting it.
                if not canvas[y + rmask, x + cmask].any():
                    best = (variant, int(x), int(y))
                    break
            else:
                continue
            break
    return best


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _rotate(points, deg):
    """Rotates an (N, 2) array of points about the origin by deg degrees."""
    if deg == 0:
        return numpy.asarray(points, dtype=float)
    a = math.radians(deg)
    cos, sin = math.cos(a), math.sin(a)
    rot = numpy.array([[cos, -sin], [sin, cos]])
    return numpy.asarray(points, dtype=float) @ rot.T


def _rasterise(polylines, origin, res):
    """
    Fills the polylines into a boolean mask using the even-odd rule (so holes in
    contours stay empty). origin is the (x, y) minimum that maps to pixel (0, 0).
    """
    shifted = [(numpy.asarray(pl, dtype=float) - origin) * res for pl in polylines]
    all_pts = numpy.vstack(shifted)
    pw = int(math.ceil(all_pts[:, 0].max())) + 1
    ph = int(math.ceil(all_pts[:, 1].max())) + 1
    counts = numpy.zeros((ph, pw), dtype=numpy.int32)
    for pl in shifted:
        rr, cc = skimage.draw.polygon(pl[:, 1], pl[:, 0], shape=(ph, pw))
        counts[rr, cc] += 1
    return (counts % 2) == 1


# ---------------------------------------------------------------------------
# SVG parsing
# ---------------------------------------------------------------------------

_STROKE_ATTRS = ("stroke", "stroke-width", "fill", "stroke-linejoin", "stroke-linecap")
_TOKEN_RE = re.compile(
    r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
)


def _load_svg(path, curve_steps):
    """
    Reads an SVG file and returns (paths, polylines), where paths is a list of
    {"d", "attrs"} for output and polylines is the flattened geometry for packing.
    """
    tree = ET.parse(path)
    paths = []
    polylines = []
    for element in tree.iter():
        if not element.tag.endswith("}path") and element.tag != "path":
            continue
        d = element.get("d")
        if not d:
            continue
        attrs = {}
        for key in _STROKE_ATTRS:
            value = element.get(key)
            if value is not None:
                attrs[key.replace("-", "_")] = value
        paths.append({"d": d, "attrs": attrs})
        polylines.extend(_flatten_path(d, curve_steps))
    return paths, polylines


def _flatten_path(d, curve_steps):
    """Flattens an SVG path 'd' string into a list of (N, 2) polylines."""
    tokens = _TOKEN_RE.findall(d)
    polylines = []
    current = []
    cur = numpy.zeros(2)
    start = numpy.zeros(2)
    cmd = None
    i = 0
    n = len(tokens)

    def number():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    def point():
        return numpy.array([number(), number()])

    while i < n:
        token = tokens[i]
        if token.isalpha():
            cmd = token
            i += 1
            if cmd in "Zz":
                if len(current) > 1:
                    current.append(start.copy())
                    polylines.append(numpy.array(current))
                current = []
                cur = start.copy()
                continue
        rel = cmd.islower()
        base = cur if rel else numpy.zeros(2)
        up = cmd.upper()

        if up == "M":
            cur = base + point()
            start = cur.copy()
            if current:
                polylines.append(numpy.array(current))
            current = [cur.copy()]
            # Subsequent implicit pairs after M are treated as L.
            cmd = "l" if rel else "L"
        elif up == "L":
            cur = base + point()
            current.append(cur.copy())
        elif up == "H":
            x = number() + (cur[0] if rel else 0.0)
            cur = numpy.array([x, cur[1]])
            current.append(cur.copy())
        elif up == "V":
            y = number() + (cur[1] if rel else 0.0)
            cur = numpy.array([cur[0], y])
            current.append(cur.copy())
        elif up == "C":
            c1 = base + point()
            c2 = base + point()
            end = base + point()
            current.extend(_cubic(cur, c1, c2, end, curve_steps))
            cur = end
        elif up == "S":
            c2 = base + point()
            end = base + point()
            current.extend(_cubic(cur, cur, c2, end, curve_steps))
            cur = end
        elif up == "Q":
            c = base + point()
            end = base + point()
            current.extend(_quad(cur, c, end, curve_steps))
            cur = end
        elif up == "T":
            end = base + point()
            current.extend(_quad(cur, cur, end, curve_steps))
            cur = end
        else:
            raise click.ClickException(f"Unsupported SVG path command: {cmd}")

    if len(current) > 1:
        polylines.append(numpy.array(current))
    return polylines


def _cubic(p0, p1, p2, p3, steps):
    """Samples a cubic Bezier, returning points after the start up to the end."""
    t = numpy.linspace(0.0, 1.0, steps + 1)[1:][:, None]
    mt = 1.0 - t
    pts = (
        mt ** 3 * p0
        + 3 * mt ** 2 * t * p1
        + 3 * mt * t ** 2 * p2
        + t ** 3 * p3
    )
    return list(pts)


def _quad(p0, p1, p2, steps):
    """Samples a quadratic Bezier, returning points after the start up to the end."""
    t = numpy.linspace(0.0, 1.0, steps + 1)[1:][:, None]
    mt = 1.0 - t
    pts = mt ** 2 * p0 + 2 * mt * t * p1 + t ** 2 * p2
    return list(pts)
