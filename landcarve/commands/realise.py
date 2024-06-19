from asyncio import base_events
import collections

import click
import numpy
import struct
import trimesh.base
import trimesh.creation

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import raster_to_array


@main.command()
@click.argument("input_path", default="-")
@click.argument("output_path")
@click.option("--xy-scale", default=1.0, help="X/Y scale to use")
@click.option("--z-scale", default=1.0, help="Z scale to use")
@click.option("--z-scale-reduction", default=1.0, help="Z scale reduction per 100m")
@click.option(
    "--minimum",
    default=0.0,
    type=float,
    help="Minimum depth (zero point) in elevation units",
)
@click.option(
    "--maximum",
    default=9999.0,
    type=float,
    help="Maxiumum depth (for flat slices) in elevation units",
)
@click.option("--base", default=1.0, help="Base thickness (in mm)")
@click.option(
    "--simplify/--no-simplify", default=True, help="Apply simplification to final model"
)
@click.option("--solid/--not-solid", default=False, help="Force a solid, square base")
@click.option("--flipy/--no-flipy", default=False, help="Flip model Y axis")
@click.option(
    "--slices", default="", help="Slice points (in elevation units) for multiple STLs"
)
@click.pass_context
def realise(
    ctx,
    input_path,
    output_path,
    xy_scale,
    z_scale,
    z_scale_reduction,
    minimum,
    maximum,
    base,
    simplify,
    solid,
    flipy,
    slices,
):
    """
    Turns a DEM array into a 3D model.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    if flipy:
        arr = numpy.flipud(arr)
    # Open the target STL file
    mesh = Mesh(scale=(xy_scale, xy_scale, z_scale), z_reduction=z_scale_reduction)
    # Apply the maximum constraint if there is one
    if maximum < 9999:
        arr = numpy.vectorize(lambda x: min(maximum, x), otypes=[object])(arr)
    # Apply the minimum constraint
    if solid:
        arr = numpy.vectorize(
            lambda x: max(0, x - minimum) if x > NODATA else 0, otypes=[object]
        )(arr)
    else:
        arr = numpy.vectorize(
            lambda x: max(0, x - minimum) if x > minimum else None, otypes=[object]
        )(arr)
    # Work out bounds and print them
    max_value = 0
    for index, value in numpy.ndenumerate(arr):
        if value and value > max_value:
            max_value = value
    print(
        f"X size: {arr.shape[1]*xy_scale:.2f}  Y size: {arr.shape[0]*xy_scale:.2f}  Z size: {max_value*z_scale:.2f}"
    )
    # For each value in the array, output appropriate polygons
    bottom = 0 - (base / z_scale)
    with click.progressbar(length=arr.shape[0], label="Calculating mesh") as bar:
        for index, value in numpy.ndenumerate(arr):
            if index[1] == 0:
                bar.update(1)
            if value is not None:
                # Work out the neighbour values
                # Arranged like so:
                #       t   tr
                #   l   c---r
                #       b
                c = (index[0], index[1], value)
                t = get_neighbour_value((index[0], index[1] - 1), arr)
                tr = get_neighbour_value((index[0] + 1, index[1] - 1), arr)
                tl = get_neighbour_value((index[0] - 1, index[1] - 1), arr)
                l = get_neighbour_value((index[0] - 1, index[1]), arr)
                r = get_neighbour_value((index[0] + 1, index[1]), arr)
                bl = get_neighbour_value((index[0] - 1, index[1] + 1), arr)
                b = get_neighbour_value((index[0], index[1] + 1), arr)
                br = get_neighbour_value((index[0] + 1, index[1] + 1), arr)
                # Centre-Right-Bottom triangle
                if r[2] is not None and b[2] is not None:
                    mesh.add_surface(c, r, b, bottom)
                    # Add diagonal edge if BR is nonexistent
                    if br[2] is None:
                        mesh.add_edge(b, r, bottom)
                    # Top edge
                    if t[2] is None and tr[2] is None:
                        mesh.add_edge(r, c, bottom)
                    # Left edge
                    if l[2] is None and bl[2] is None:
                        mesh.add_edge(c, b, bottom)
                # Top-centre-left triangle
                if t[2] is not None and l[2] is not None:
                    mesh.add_surface(t, c, l, bottom)
                    # Add diagonal edge if TL is nonexistent
                    if tl[2] is None:
                        mesh.add_edge(t, l, bottom)
                    # Right edge
                    if r[2] is None and tr[2] is None:
                        mesh.add_edge(c, t, bottom)
                    # Bottom edge
                    if b[2] is None and bl[2] is None:
                        mesh.add_edge(l, c, bottom)
                # Top-right-center triangle (if tr doesn't exist)
                if t[2] is not None and r[2] is not None and tr[2] is None:
                    mesh.add_surface(t, r, c, bottom)
                    # Also implies there must be an edge there
                    mesh.add_edge(r, t, bottom)
                    # See if it needs a left edge
                    if l[2] is None and tl[2] is None:
                        mesh.add_edge(t, c, bottom)
                    # Bottom edge
                    if b[2] is None and br[2] is None:
                        mesh.add_edge(c, r, bottom)
                # Left-center-bottom triangle (if bl doesn't exist)
                if l[2] is not None and b[2] is not None and bl[2] is None:
                    mesh.add_surface(l, c, b, bottom)
                    # Also implies there must be an edge there
                    mesh.add_edge(l, b, bottom)
                    # See if it needs a right edge
                    if r[2] is None and br[2] is None:
                        mesh.add_edge(b, c, bottom)
                    # And a top edge
                    if t[2] is None and tr[2] is None:
                        mesh.add_edge(c, l, bottom)
    # Simplify
    if simplify:
        click.echo("Simplifying mesh  [", err=True, nl=False)
        total_removed = 0
        while True:
            removed = mesh.simplify()
            click.echo(".", nl=False)
            if not removed:
                break
            total_removed += removed
        click.echo("] %i vertices removed" % total_removed)
    tmesh = mesh.to_trimesh()
    # Slice
    if slices:
        click.echo("Slicing mesh  [", err=True, nl=False)
        bounds = [
            [tmesh.bounds[0][0] - 1, tmesh.bounds[0][2] - 1, -1],
            [tmesh.bounds[1][0] + 1, tmesh.bounds[1][1] + 1, -1],
        ]
        slices = [float(val.strip()) for val in slices.strip().split(",")] + [9999]
        for slice in slices:
            click.echo(f"{slice} ", nl=False)
            # Create a box to slice by
            bounds[0][2] = bounds[1][2]
            bounds[1][2] = (slice - minimum) * z_scale
            box = trimesh.creation.box(bounds=bounds)
            slice_mesh = trimesh.boolean.intersection([tmesh, box])
            slice_mesh.export(output_path.replace(".stl", f".{slice}.stl"))
        click.echo("]")
    # All done!
    click.echo("Writing STL...", err=True)
    tmesh.export(output_path)


def get_neighbour_value(index, arr):
    """
    Gets a neighbour value. Puts None in place for NODATA or edge of array.
    """
    if (
        index[0] < 0
        or index[0] >= arr.shape[0]
        or index[1] < 0
        or index[1] >= arr.shape[1]
    ):
        return (index[0], index[1], None)
    else:
        value = arr[index]
        return (index[0], index[1], value)


class Mesh:
    """
    Represents a mesh of the geography.
    """

    def __init__(self, scale, z_reduction=1):
        self.scale = scale or (1, 1, 1)
        self.z_reduction = z_reduction
        # Dict of (x, y, z): index
        self.vertices = collections.OrderedDict()
        # List of (v1, v2, v3, normal)
        self.faces: list[tuple[tuple[float, float, float], float, float, float]] = []

    def vertex_index(self, vertex):
        """
        Returns the vertex's index, adding it if needed
        """
        assert len(vertex) == 3
        z_units = vertex[2] / 100.0
        z_scale = self.scale[2] * (self.z_reduction**z_units)
        vertex = (
            vertex[0] * self.scale[0],
            vertex[1] * self.scale[1],
            vertex[2] * z_scale,
        )
        if vertex not in self.vertices:
            self.vertices[vertex] = len(self.vertices)
        return self.vertices[vertex]

    def add_triangle(self, point1, point2, point3):
        """
        Adds a single triangle
        """
        # Get vertex indices
        i1 = self.vertex_index(point1)
        i2 = self.vertex_index(point2)
        i3 = self.vertex_index(point3)
        # Calculate normal (clockwise)
        u = (point2[0] - point1[0], point2[1] - point1[1], point2[2] - point1[2])
        v = (point3[0] - point1[0], point3[1] - point1[1], point3[2] - point1[2])
        normal = (
            (u[1] * v[2]) - (u[2] * v[1]),
            (u[2] * v[0]) - (u[0] * v[2]),
            (u[0] * v[1]) - (u[1] * v[0]),
        )
        normal_magnitude = (
            (normal[0] ** 2) + (normal[1] ** 2) + (normal[2] ** 2)
        ) ** 0.5
        normal = (
            normal[0] / normal_magnitude,
            normal[1] / normal_magnitude,
            normal[2] / normal_magnitude,
        )
        # Add face
        self.faces.append((normal, i1, i2, i3))

    def add_quad(self, point1, point2, point3, point4):
        """
        Adds a quad to the file, made out of two facets. Pass vertices in
        clockwise order.
        """
        self.add_triangle(point1, point2, point4)
        self.add_triangle(point2, point3, point4)

    def add_surface(self, point1, point2, point3, bottom):
        """
        Adds a facet with a matching flat bottom polygon.
        Points should be clockwise looking from the top.
        """
        self.add_triangle(
            (point1[0], point1[1], point1[2]),
            (point2[0], point2[1], point2[2]),
            (point3[0], point3[1], point3[2]),
        )
        self.add_triangle(
            (point1[0], point1[1], bottom),
            (point3[0], point3[1], bottom),
            (point2[0], point2[1], bottom),
        )

    def add_edge(self, point1, point2, bottom):
        """
        Adds a quad to form an edge between the two vertices.
        Vertices should be left, right looking from the outside of the model.
        """
        self.add_quad(
            (point1[0], point1[1], point1[2]),
            (point2[0], point2[1], point2[2]),
            (point2[0], point2[1], bottom),
            (point1[0], point1[1], bottom),
        )

    def to_trimesh(self):
        """
        Returns a PyMesh representation of us
        """
        # Sort vertices by their index
        vertices_by_index = [(i, v) for v, i in self.vertices.items()]
        vertices_by_index.sort()
        vertices = numpy.array([v for i, v in vertices_by_index])
        # Extract faces into triples
        faces = numpy.array([[v1, v2, v3] for n, v1, v2, v3 in self.faces])

        return trimesh.base.Trimesh(vertices, faces)

    def simplify(self):
        """
        Simplifies the mesh via edge-merging. Goes through all edges, and sees
        if all faces attached to that edge have the same normal. If so, collapses
        it.
        """
        # Create a map of vertex indexes to the normals of the faces attached to them,
        # and vertices to their neighbours
        non_flat_vertices = set()
        vertex_face_normals = {}
        vertex_neighbours = {v: [] for v in self.vertices.values()}
        for normal, v1, v2, v3 in self.faces:
            # Work out if it has flat normals
            for v in (v1, v2, v3):
                if v not in non_flat_vertices:
                    if v in vertex_face_normals:
                        if vertex_face_normals[v] != normal:
                            non_flat_vertices.add(v)
                            del vertex_face_normals[v]
                    else:
                        vertex_face_normals[v] = normal
            # Add it to the neighbour graph
            vertex_neighbours[v1].extend([v2, v3])
            vertex_neighbours[v2].extend([v1, v3])
            vertex_neighbours[v3].extend([v1, v2])
        # Go through edges, and remove those whose normals match.
        # Keep track of tainted vertices that we can't touch this iteration.
        tainted_vertices = set()
        merged_vertices = {}
        for index, vertex in enumerate(self.vertices):
            # Skip non-flat vertices
            if index not in vertex_face_normals:
                continue
            # Skip vertices whose neighbours were already touched
            if index in tainted_vertices:
                continue
            # Skip vertices which have non-flat neighbours
            if not all(
                neighbour in vertex_face_normals
                for neighbour in vertex_neighbours[index]
            ):
                continue
            # See if there's a neighbour we can merge with
            for neighbour in vertex_neighbours[index]:
                if (
                    neighbour in vertex_face_normals
                    and vertex_face_normals[neighbour] == vertex_face_normals[index]
                ):
                    # Mark them for merge
                    merged_vertices[index] = neighbour
                    # Mark them as tainted so we don't revisit them
                    tainted_vertices.add(index)
                    tainted_vertices.add(neighbour)
                    break
        # Rewrite mesh with the new vertices and faces
        new_vertices = collections.OrderedDict()
        new_faces = []
        vertex_map = {}  # Maps old index to new one
        # First, write all unmerged vertices out
        for index, vertex in enumerate(self.vertices):
            if index not in merged_vertices:
                vertex_map[index] = len(new_vertices)
                new_vertices[vertex] = len(new_vertices)
        # Then, add mappings for the merged vertices
        for vertex, merged_to in merged_vertices.items():
            vertex_map[vertex] = vertex_map[merged_to]
        # Finally, rewrite all the faces, removing those that are now zero sized
        for normal, v1, v2, v3 in self.faces:
            new1 = vertex_map[v1]
            new2 = vertex_map[v2]
            new3 = vertex_map[v3]
            # Skip face if it's now zero size
            if new1 == new2 or new2 == new3 or new3 == new1:
                continue
            new_faces.append((normal, new1, new2, new3))
        self.vertices = new_vertices
        self.faces = new_faces
        return len(merged_vertices)

    def save(self, path):
        """
        Saves the mesh as an STL file
        """
        # Invert vertices to be mapped by index (well, a list)
        vertex_list = list(self.vertices.keys())
        # Write STL file
        with open(path, "wb") as fh:
            # Write STL header
            fh.write(b" " * 80)  # Textual header
            fh.write(struct.pack(b"<L", len(self.faces)))  # The number of facets
            # Write facets
            for normal, i1, i2, i3 in self.faces:
                vertex1 = vertex_list[i1]
                vertex2 = vertex_list[i2]
                vertex3 = vertex_list[i3]
                # Write out entry
                fh.write(
                    struct.pack(
                        b"<ffffffffffffH",
                        normal[0],
                        normal[1],
                        normal[2],
                        vertex1[0],
                        vertex1[1],
                        vertex1[2],
                        vertex2[0],
                        vertex2[1],
                        vertex2[2],
                        vertex3[0],
                        vertex3[1],
                        vertex3[2],
                        0,
                    )
                )
