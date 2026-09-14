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
@click.option(
    "--fill-color",
    "fill_color",
    default=None,
    help="If set, colour the lower part of every layer in this constant colour "
    "(hex like #ff8800 or a name like 'red'), keeping each layer's own colour "
    "only for the top --top mm of its height.",
)
@click.option(
    "--top",
    default=1.0,
    type=float,
    help="Height in mm at the top of each layer kept in the layer's own colour "
    "when --fill-color is set; the rest of the height takes the fill colour.",
)
@click.option(
    "--water",
    "water_path",
    default=None,
    type=str,
    help="An SVG (as produced by contour-svg) whose filled regions are water. "
    "Wherever it overlaps a layer, that part of the layer's visible surface is "
    "given --water-color instead of the layer's own colour.",
)
@click.option(
    "--water-color",
    "water_color",
    default="#3376b9",
    help="Colour used for the parts of each layer covered by --water.",
)
@click.argument("output_path")
def layer_3mf(
    layers,
    output_path,
    extrude,
    width,
    curve_steps,
    fill_color,
    top,
    water_path,
    water_color,
):
    """
    Stacks several contour SVGs (as produced by contour-svg) into a single 3MF
    file, one extruded layer per SVG, each in its own colour.

    Every SVG is treated as a filled outline (using the even-odd rule, so holes
    in contours stay hollow), extruded by --extrude mm. Layers are stacked in the
    order given: the first --layer sits at the bottom, each subsequent one resting
    directly on top of the previous. All SVGs share one transform so they stay
    aligned, scaled so the whole model is --width mm wide.

    With --fill-color, the lower part of every layer is given that constant colour
    and only the top --top mm of each layer keeps its own colour.

    With --water, the regions of each layer that fall under the water mask take
    --water-color on their visible surface, so lakes, rivers and sea read as water
    whichever layer they happen to sit on.
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

    # An optional secondary colour for the lower part of every layer.
    fill_rgba = parse_color(fill_color) if fill_color is not None else None

    # The optional water mask, in the same coordinate space as the layer SVGs.
    water_rings = None
    water_rgba = parse_color(water_color)
    if water_path is not None:
        _paths, water_rings = _load_svg(water_path, curve_steps)
        if not water_rings:
            click.echo(f"No water geometry found in {water_path}", err=True)
            water_rings = None

    # Work out one shared transform from the combined bounding box of every layer,
    # so the layers stay aligned and the model ends up --width mm wide. The water
    # mask is deliberately left out of this: it covers the whole raster rather than
    # just the contoured part, so including it would move and rescale the model.
    all_points = numpy.vstack([r for layer in loaded for r in layer["rings"]])
    min_xy = all_points.min(axis=0)
    max_xy = all_points.max(axis=0)
    span = max_xy - min_xy
    if span[0] <= 0:
        raise click.ClickException("Input SVGs have no horizontal extent")
    scale = width / span[0]

    def to_cross_section(rings):
        """
        Turns SVG-space rings into a model-space CrossSection.

        X/Y are scaled to mm; Y is flipped so the model is upright (SVG Y points
        down) and sits in the positive quadrant. Every layer and the water mask go
        through this same transform, so they all stay registered with each other.
        """
        transformed = []
        for ring in rings:
            ring = numpy.asarray(ring, dtype=float)
            x = (ring[:, 0] - min_xy[0]) * scale
            y = (max_xy[1] - ring[:, 1]) * scale
            transformed.append(numpy.column_stack([x, y]).tolist())
        return manifold3d.CrossSection(transformed, manifold3d.FillRule.EvenOdd)

    water_cross = to_cross_section(water_rings) if water_rings else None

    # Build one extruded mesh per layer, stacked in Z.
    objects = []
    for index, layer in enumerate(loaded):
        cross = to_cross_section(layer["rings"])
        # Rest this layer on top of the ones below it.
        base_z = index * extrude

        if fill_rgba is not None and 0 < top < extrude:
            # Split the layer: a fill-coloured base and the top --top mm in the
            # layer's own colour (or the water colour where water covers it).
            bottom_height = extrude - top
            layer_objects = [
                _extruded_object(cross, bottom_height, base_z, fill_rgba),
            ] + _coloured_slice(
                cross,
                water_cross,
                top,
                base_z + bottom_height,
                layer["rgba"],
                water_rgba,
            )
        else:
            # No separate top slice, so water has to claim the whole layer height
            # or it would not be visible at all.
            layer_objects = _coloured_slice(
                cross, water_cross, extrude, base_z, layer["rgba"], water_rgba
            )

        objects.extend(layer_objects)
        triangle_count = sum(len(o["triangles"]) for o in layer_objects)
        click.echo(
            f"Layer {index + 1}/{len(loaded)}: {layer['name']} "
            f"({triangle_count} triangles)"
        )

    write_3mf(output_path, objects)
    click.echo(
        f"Wrote {len(loaded)} layer(s) as {len(objects)} object(s), "
        f"{width:.1f}mm wide x {len(loaded) * extrude:.1f}mm tall -> {output_path}"
    )


def _coloured_slice(cross, water_cross, height, z_offset, rgba, water_rgba):
    """
    Extrudes one slice of a layer, split into dry and wet parts.

    Without a water mask this is a single object in the layer's own colour. With
    one, the slice is cut into the part the water covers (water_rgba) and the part
    it does not (rgba); either part is omitted when it comes out empty, so layers
    that are entirely dry or entirely underwater stay a single mesh.
    """
    if water_cross is None:
        return [_extruded_object(cross, height, z_offset, rgba)]
    wet = cross ^ water_cross
    if wet.is_empty():
        return [_extruded_object(cross, height, z_offset, rgba)]
    objects = []
    dry = cross - water_cross
    if not dry.is_empty():
        objects.append(_extruded_object(dry, height, z_offset, rgba))
    objects.append(_extruded_object(wet, height, z_offset, water_rgba))
    return objects


def _extruded_object(cross, height, z_offset, rgba):
    """Extrudes a cross-section to a given height, lifted to z_offset, in one colour."""
    mesh = cross.extrude(height).to_mesh()
    vertices = numpy.asarray(mesh.vert_properties)[:, :3].copy()
    vertices[:, 2] += z_offset
    triangles = numpy.asarray(mesh.tri_verts)
    return {"vertices": vertices, "triangles": triangles, "rgba": rgba}


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
