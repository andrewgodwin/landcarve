import zipfile

import click
import manifold3d
import numpy

from landcarve.cli import main
from landcarve.commands.pack_svg import _load_svg


@main.command()
@click.option(
    "--layer",
    "layers",
    multiple=True,
    nargs=2,
    metavar="SVG COLOR",
    required=True,
    help="An SVG file and its colour (hex like #ff8800 or a name like 'red'). "
    "Repeat once per layer; the first --layer is the bottom of the stack.",
)
@click.option(
    "--extrude",
    default=1.0,
    type=float,
    help="Height each layer is extruded by, in mm",
)
@click.option(
    "--width",
    default=150.0,
    type=float,
    help="Target width of the model in mm (the SVGs are scaled to match)",
)
@click.option(
    "--curve-steps",
    default=12,
    type=int,
    help="Segments used to flatten Bezier curves from the SVGs",
)
@click.argument("output_path")
def layer_3mf(layers, output_path, extrude, width, curve_steps):
    """
    Stacks several contour SVGs (as produced by contour-svg) into a single 3MF
    file, one extruded layer per SVG, each in its own colour.

    Every SVG is treated as a filled outline (using the even-odd rule, so holes
    in contours stay hollow), extruded by --extrude mm. Layers are stacked in the
    order given: the first --layer sits at the bottom, each subsequent one resting
    directly on top of the previous. All SVGs share one transform so they stay
    aligned, scaled so the whole model is --width mm wide.
    """
    # Load every layer's geometry as a list of flattened rings (closed polylines).
    loaded = []
    for path, color in layers:
        _paths, polylines = _load_svg(path, curve_steps)
        if not polylines:
            click.echo(f"Skipping {path}: no drawable paths found", err=True)
            continue
        loaded.append({"name": path, "rgba": parse_color(color), "rings": polylines})

    if not loaded:
        raise click.ClickException("No usable layers found in the input files")

    # Work out one shared transform from the combined bounding box of every layer,
    # so the layers stay aligned and the model ends up --width mm wide.
    all_points = numpy.vstack([r for layer in loaded for r in layer["rings"]])
    min_xy = all_points.min(axis=0)
    max_xy = all_points.max(axis=0)
    span = max_xy - min_xy
    if span[0] <= 0:
        raise click.ClickException("Input SVGs have no horizontal extent")
    scale = width / span[0]

    # Build one extruded mesh per layer, stacked in Z.
    objects = []
    for index, layer in enumerate(loaded):
        # Transform points into model space. X/Y are scaled to mm; Y is flipped so
        # the model is upright (SVG Y points down) and sits in the positive quadrant.
        rings = []
        for ring in layer["rings"]:
            ring = numpy.asarray(ring, dtype=float)
            x = (ring[:, 0] - min_xy[0]) * scale
            y = (max_xy[1] - ring[:, 1]) * scale
            rings.append(numpy.column_stack([x, y]))

        cross = manifold3d.CrossSection(
            [r.tolist() for r in rings], manifold3d.FillRule.EvenOdd
        )
        mesh = cross.extrude(extrude).to_mesh()
        vertices = numpy.asarray(mesh.vert_properties)[:, :3].copy()
        # Rest this layer on top of the ones below it.
        vertices[:, 2] += index * extrude
        triangles = numpy.asarray(mesh.tri_verts)

        objects.append(
            {"vertices": vertices, "triangles": triangles, "rgba": layer["rgba"]}
        )
        click.echo(
            f"Layer {index + 1}/{len(loaded)}: {layer['name']} "
            f"({len(triangles)} triangles)"
        )

    write_3mf(output_path, objects)
    click.echo(
        f"Wrote {len(objects)} layer(s), "
        f"{width:.1f}mm wide x {len(objects) * extrude:.1f}mm tall -> {output_path}"
    )


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

# A small set of CSS colour names so the common cases work without hex codes.
_NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "lime": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "brown": (165, 42, 42),
    "grey": (128, 128, 128),
    "gray": (128, 128, 128),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "pink": (255, 192, 203),
    "tan": (210, 180, 140),
}


def parse_color(value):
    """Parses a hex colour (#rgb, #rrggbb, #rrggbbaa) or name into an RGBA tuple."""
    text = value.strip().lower()
    if text in _NAMED_COLORS:
        return _NAMED_COLORS[text] + (255,)
    hexpart = text[1:] if text.startswith("#") else text
    try:
        if len(hexpart) == 3:
            r, g, b = (int(c * 2, 16) for c in hexpart)
            return (r, g, b, 255)
        if len(hexpart) in (6, 8):
            channels = [int(hexpart[i : i + 2], 16) for i in range(0, len(hexpart), 2)]
            if len(channels) == 3:
                channels.append(255)
            return tuple(channels)
    except ValueError:
        pass
    raise click.ClickException(f"Unrecognised colour: {value}")


# ---------------------------------------------------------------------------
# 3MF writing
# ---------------------------------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" '
    'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)


def write_3mf(path, objects):
    """
    Writes a list of coloured meshes to a 3MF file.

    Each object is a dict with "vertices" (N, 3), "triangles" (M, 3) and "rgba".
    Colours are written as a material colour group (the 3MF material extension)
    and referenced on *every triangle* via pid/p1. Slicers such as Bambu Studio
    only detect colour when it lives on the faces (face colouring); an
    object-level material default alone is silently ignored on import.
    """
    # Build a deduplicated colour palette so equal colours share one index.
    palette = []
    palette_index = {}
    for obj in objects:
        rgba = tuple(obj["rgba"])
        if rgba not in palette_index:
            palette_index[rgba] = len(palette)
            palette.append(rgba)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">',
        '<resources>',
        '<m:colorgroup id="1">',
    ]
    for r, g, b, a in palette:
        parts.append(f'<m:color color="#{r:02X}{g:02X}{b:02X}{a:02X}"/>')
    parts.append("</m:colorgroup>")

    # Object ids start at 2 (the colour group is id 1).
    for index, obj in enumerate(objects):
        color_index = palette_index[tuple(obj["rgba"])]
        # Reference the colour at the object level (default) and on every face,
        # so both object-aware and face-colour-aware slicers pick it up.
        parts.append(
            f'<object id="{index + 2}" type="model" pid="1" pindex="{color_index}">'
            "<mesh><vertices>"
        )
        for vx, vy, vz in obj["vertices"]:
            parts.append(f'<vertex x="{vx:.5f}" y="{vy:.5f}" z="{vz:.5f}"/>')
        parts.append("</vertices><triangles>")
        for t1, t2, t3 in obj["triangles"]:
            parts.append(
                f'<triangle v1="{t1}" v2="{t2}" v3="{t3}" '
                f'pid="1" p1="{color_index}"/>'
            )
        parts.append("</triangles></mesh></object>")

    parts.append("</resources><build>")
    for index in range(len(objects)):
        parts.append(f'<item objectid="{index + 2}"/>')
    parts.append("</build></model>")

    model_xml = "".join(parts)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("3D/3dmodel.model", model_xml)
