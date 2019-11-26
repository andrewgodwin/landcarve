import click
import numpy
import struct

from landcarve.cli import main
from landcarve.constants import NODATA
from landcarve.utils.io import raster_to_array


@main.command()
@click.argument("input_path", default="-")
@click.argument("output_path")
@click.option("--xy-scale", default=1, help="X/Y scale to use")
@click.option("--z-scale", default=1, help="Z scale to use")
@click.option("--minimum", default=0, help="Minimum depth (zero point)")
@click.option("--thickness", default=1, help="Base thickness")
@click.pass_context
def realise(ctx, input_path, output_path, xy_scale, z_scale, minimum, thickness):
    """
    Turns a DEM array into a 3D model.
    """
    # Load the file using GDAL
    arr = raster_to_array(input_path)
    # Open the target STL file
    stl = STLWriter(output_path, xy_scale=xy_scale, z_scale=z_scale)
    # For each value in the array, output appropriate polygons
    bottom = 0 - (thickness / z_scale)
    with click.progressbar(length=arr.shape[0], label="Writing STL") as bar:
        for index, value in numpy.ndenumerate(arr):
            if index[1] == 0:
                bar.update(1)
            if NODATA < value < minimum:
                value = minimum
            if value > NODATA:
                # Work out the neighbour values
                # Arranged like so:
                #       t   tr
                #   l   c---r   r2
                #   bl  b---br  br2
                #       b2  b2r
                c = (index[0], index[1], value)
                t = get_neighbour_value((index[0], index[1] - 1), arr, NODATA)
                tr = get_neighbour_value((index[0] + 1, index[1] - 1), arr, NODATA)
                l = get_neighbour_value((index[0] - 1, index[1]), arr, NODATA)
                r = get_neighbour_value((index[0] + 1, index[1]), arr, NODATA)
                r2 = get_neighbour_value((index[0] + 2, index[1]), arr, NODATA)
                bl = get_neighbour_value((index[0] - 1, index[1] + 1), arr, NODATA)
                b = get_neighbour_value((index[0], index[1] + 1), arr, NODATA)
                br = get_neighbour_value((index[0] + 1, index[1] + 1), arr, NODATA)
                br2 = get_neighbour_value((index[0] + 2, index[1] + 1), arr, NODATA)
                b2 = get_neighbour_value((index[0], index[1] + 2), arr, NODATA)
                b2r = get_neighbour_value((index[0] + 1, index[1] + 2), arr, NODATA)
                # Centre-Right-Bottom triangle
                if r[2] is not None and b[2] is not None and br[2] is not None:
                    stl.add_facet(c[0], c[1], c[2], r[0], r[1], r[2], b[0], b[1], b[2])
                    stl.add_facet(
                        c[0], c[1], bottom, b[0], b[1], bottom, r[0], r[1], bottom
                    )
                    # Right-bottom-bottomright triangle
                    #if br is not None:
                    stl.add_facet(
                        r[0], r[1], r[2], br[0], br[1], br[2], b[0], b[1], b[2]
                    )
                    stl.add_facet(
                        r[0], r[1], bottom, b[0], b[1], bottom, br[0], br[1], bottom
                    )
                    # Top edge
                    if t[2] is None or tr[2] is None:
                        stl.add_facet(
                            c[0], c[1], c[2], c[0], c[1], bottom, r[0], r[1], r[2]
                        )
                        stl.add_facet(
                            c[0], c[1], bottom, r[0], r[1], bottom, r[0], r[1], r[2]
                        )
                    # Right edge
                    if r2[2] is None or br2[2] is None:
                        stl.add_facet(
                            r[0], r[1], r[2], r[0], r[1], bottom, br[0], br[1], br[2]
                        )
                        stl.add_facet(
                            r[0],
                            r[1],
                            bottom,
                            br[0],
                            br[1],
                            bottom,
                            br[0],
                            br[1],
                            br[2],
                        )
                    # Bottom edge
                    if b2[2] is None or b2r[2] is None:
                        stl.add_facet(
                            br[0], br[1], br[2], br[0], br[1], bottom, b[0], b[1], b[2]
                        )
                        stl.add_facet(
                            br[0], br[1], bottom, b[0], b[1], bottom, b[0], b[1], b[2]
                        )
                    # Left edge
                    if l[2] is None or bl[2] is None:
                        stl.add_facet(
                            b[0], b[1], b[2], b[0], b[1], bottom, c[0], c[1], c[2]
                        )
                        stl.add_facet(
                            b[0], b[1], bottom, c[0], c[1], bottom, c[0], c[1], c[2]
                        )
    # All done!
    stl.close()


def get_neighbour_value(index, arr, NODATA):
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
        if value <= NODATA:
            return (index[0], index[1], None)
        else:
            return (index[0], index[1], value)


class STLWriter:
    """
    Writes to STL files.
    """

    def __init__(self, path, xy_scale=1, z_scale=1):
        self.path = path
        self.xy_scale = xy_scale
        self.z_scale = z_scale
        self.fh = open(self.path, "wb")
        self.num_facets = 0
        self.write_header()

    def write_header(self):
        """
        Writes the STL header. Called once on creation and once on close.
        """
        self.fh.seek(0)
        # Textual header
        self.fh.write(b" " * 80)
        # The number of facets
        self.fh.write(struct.pack(b"<L", self.num_facets))

    def close(self):
        """
        Closes the STL file cleanly.
        """
        self.write_header()
        self.fh.close()

    def add_facet(self, x1, y1, z1, x2, y2, z2, x3, y3, z3):
        """
        Adds a single triangle to the STL file.
        """
        # Calculate normal - clockwise vectors from solid face
        u = (x2 - x1, y2 - y1, z2 - z1)
        v = (x3 - x1, y3 - y1, z3 - z1)
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
        # Write out entry
        self.fh.write(
            struct.pack(
                b"<ffffffffffffH",
                normal[0],
                normal[1],
                normal[2],
                x1 * self.xy_scale,
                y1 * self.xy_scale,
                z1 * self.z_scale,
                x2 * self.xy_scale,
                y2 * self.xy_scale,
                z2 * self.z_scale,
                x3 * self.xy_scale,
                y3 * self.xy_scale,
                z3 * self.z_scale,
                0,
            )
        )
        self.num_facets += 1
