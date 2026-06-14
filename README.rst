Landcarve
=========

A collection of tools for making 3D models and similar things out of GIS data.
Designed to be run as a pipeline, though the individual tools can be run too.


General Use
-----------

Define a pipeline in a text file, with one command per line (there are
examples in the ``examples/`` directory). The commands should not have the
``landcarve`` prefix on them; for example::

    # Decimate down to a small size
    decifit --xy-steps=50

    # Render to an STL
    realise --xy-scale=0.01 --z-scale=0.01 --base=0.2 --solid

Then, run the pipeline with an input and output path, like so::

    landcarve pipeline national-parks.txt input.geotiff output.stl

You can read more about the individual commands below. If you want to get going
directly with an example, download the .asc file linked from the
``examples/london-tiles.txt`` pipeline, and run::

    landcarve pipeline examples/london-tiles.txt tq3780_DSM_1m.asc output.stl


Installation
------------

This isn't on PyPI yet, so clone the repository and run ``pip install -e .``.

Installing GDAL can be a particular pain; if your OS offers it, I highly
recommend installing a Python 3 GDAL package from there. On Ubuntu/Debian, this
is ``python3-gdal``.


Tips
----

There is no true "right scale" for geographic data due to map projections,
so you need to take care if you want to get things coming out at an exact scale,
or consistent with other prints.

Generally, the horizontal (X & Y) scale is determined by the number of
rows/columns in your data, and all the tools will try and maintain its aspect
ratio. ``decifit`` allows you to shrink it down while maintaining the ratio,
while ``realise`` will simply map one column/row to one unit in the final model
unless you use ``--xy-scale``.

The vertical (Z) scale is more flexible, as generally printing with the same
scale on Z as you have on X and Y will result in things that look too flat -
the sense of perception of height we have for models is weird.

There's two ways of dealing with Z - always expanding it to a certain height
in the resulting model (``zfit``), or scaling it consistently with a factor
(``--z-scale`` on ``realise``).

``zfit`` is for small, one-off items that aren't
going to be directly compared to each other, and are large-scale geography -
this is what I use for National Park miniatures, for example, as you always
want to see the geographic detail, and I don't want the same scale across all
the parks (otherwise the mountainous ones will cause the rest to look basically
flat).

The ``--z-scale`` option, on the other hand, is for when you want to print
a set of tiles that will all sit next to each other. Keep it the same, and your
heights will all line up.

If you're printing an area that is all at elevation, you will need to either use
``zfit`` (which will auto-trim to the lowest point you have), or pass ``--minimum``
to ``realise`` to set the "base level" of your model. Anything below the minimum
will be rendered as flat; this is also important if you have holes in your
model that go below sea level (e.g. excavations).

Finally, realise that the runtime (and memory usage) of this code goes up
rather quickly as you increase the size of the grid being used.
Always use ``decifit`` as the first element in a pipeline, and try to keep
under 1000 in each dimension; 500 tends to be a good tradeoff.




Commands
--------

Commands are listed alphabetically. Run ``landcarve <command> --help`` for the
full option list. Most commands take an input path and an output path.


bulkget
~~~~~~~

Downloads only the "interesting" URLs from a text file list. Designed for use
with the USGS National Map downloader.


contour-image
~~~~~~~~~~~~~

Slices terrain into contour layers and outputs a print image and cut line per
layer, laid out onto printable pages. Must be the last step in a pipeline.

Options:
    * ``--min-object``: Ignore objects smaller than this (percent). Default: 0.05
    * ``--min-hole``: Fill holes smaller than this (percent). Default: 0.02
    * ``--simp``: Contour simplification coefficient. Default: 0.5
    * ``--bleed``: Pixels to bleed over the image for cutting. Default: 3
    * ``--line-scale``: Scale for graphical elements. Default: 2
    * ``--page-size``: Output page size in pixels. Default: input size
    * ``--rigid/--non-rigid``: Leave holes inside terrain to save material. Default: ``--non-rigid``
    * ``--construction-only/--with-pieces``: Only output construction images. Default: ``--with-pieces``


contour-svg
~~~~~~~~~~~

Extracts a single contour line at a given height from a raster and outputs it as
a smoothed SVG path.

Options:
    * ``--simp``: Simplification coefficient (0 to skip). Default: 0.2
    * ``--smooth``: Gaussian smoothing sigma in pixels (0 to skip). Default: 0.0
    * ``--tension``: Catmull-Rom tension for smoothing. Default: 3.0
    * ``--min-object``: Remove regions smaller than this (percent). Default: 0.2
    * ``--min-hole``: Fill holes smaller than this (percent). Default: 0.1
    * ``--min-points``: Minimum points a contour must have. Default: 4
    * ``--stroke-width``: SVG stroke width. Default: 1.0
    * ``--stroke-color``: SVG stroke colour. Default: black
    * ``--fill-color``: SVG fill colour. Default: none


decifit
~~~~~~~

Scales a raster down to fit within a number of cells in X/Y, preserving aspect
ratio. Does not touch Z/values.

Options:
    * ``-x``: Maximum number of steps on X and Y. Default: 1000


decimate
~~~~~~~~

Scales a raster down by an integer divisor, preserving aspect ratio.

Options:
    * ``-d``: Divisor on the number of steps. Default: 2


elevalue
~~~~~~~~

Outputs elevation values only where a second discrete-valued raster (e.g.
landcover) falls within a range. Useful for masking water or land types.

Options:
    * ``-m``: Minimum discrete value to preserve (inclusive).
    * ``-x``: Maximum discrete value to preserve (inclusive).


exactfit
~~~~~~~~

Scales a raster to an exact number of cells in X and Y (aspect ratio not
preserved).

Options:
    * ``-x``: Exact number of steps on X. Default: 1000
    * ``-y``: Exact number of steps on Y. Default: 1000


fixnodata
~~~~~~~~~

Pins NODATA values to the internal value of -1000. Use as a pipeline step when
source data uses a different NODATA boundary.

Options:
    * ``--nodata``: NODATA boundary for input data. Default: 0


flipy
~~~~~

Flips the raster vertically (swaps up and down).


lasdem
~~~~~~

Turns one or more LAS/LAZ point cloud files into a GeoTIFF DEM, thinning by
highest return and filling voids.

Options:
    * ``--snap`` (``-s``): Snap/thinning resolution. Default: 1
    * ``--void-distance`` (``-d``): Max distance to fill voids from. Default: 10
    * ``--z-limit`` (``-z``): Maximum elevation to trust. Default: 4000
    * ``--despeckle``: Despeckle strength (0 to disable). Default: 1
    * ``--ignore-header-range``: Ignore the header's stated value range. Default: off


layer-3mf
~~~~~~~~~

Stacks several contour SVGs into a single 3MF file, one extruded coloured layer
per SVG, aligned and scaled together.

Options:
    * ``--layer``: An SVG file and its colour; repeat once per layer (bottom first).
    * ``--extrude``: Height each layer is extruded by, in mm. Default: 1.0
    * ``--width``: Target model width in mm. Default: 150.0
    * ``--curve-steps``: Segments used to flatten Bezier curves. Default: 12


merge
~~~~~

Merges several DEMs together into one.


pack-svg
~~~~~~~~

Packs several contour SVGs into a single sheet, nesting the pieces as tightly as
possible. Original path data is preserved; only a transform is applied.

Options:
    * ``--resolution``: Mask pixels per SVG unit for packing. Default: 1.0
    * ``--margin``: Minimum gap between pieces, in SVG units. Default: 2.0
    * ``--rotations``: Discrete rotations to try per piece. Default: 4
    * ``--width``: Output sheet width (0 = approx square). Default: 0.0
    * ``--curve-steps``: Segments used to flatten Bezier curves. Default: 12


pipeline
~~~~~~~~

Runs a series of commands from a pipeline file, passing files between steps.

Options:
    * ``--extension``: Output file extension. Default: .stl


realise
~~~~~~~

Turns a DEM heightmap into a 3D STL model. By default one grid cell maps to one
output unit.

Options:
    * ``--xy-scale``: Scale factor in X/Y. Default: 1
    * ``--z-scale``: Scale factor in Z. Default: 1
    * ``--z-scale-reduction``: Z scale reduction per 100m. Default: 1
    * ``--minimum``: Zero/base elevation; detail below is rendered flat. Default: 0
    * ``--maximum``: Elevation above which slices are flattened. Default: 9999
    * ``--base``: Base thickness below the model, in output units. Default: 1
    * ``--simplify/--no-simplify``: Merge flat areas in the mesh. Default: ``--simplify``
    * ``--solid/--not-solid``: Force a solid, square base (no holes). Default: ``--not-solid``
    * ``--flipy/--no-flipy``: Flip the model's Y axis. Default: ``--no-flipy``
    * ``--thin/--not-thin``: Thin surface only, no solid base. Default: ``--not-thin``
    * ``--slices``: Elevation slice points for multiple output STLs.


smooth
~~~~~~

Smooths heightmap data to remove jagged heights from reflections or laser
errors. Higher factor smooths more.

Options:
    * ``--factor``: Smoothing factor. Default: 1


stats
~~~~~

Prints statistics (value range, etc.) about a DEM.


step
~~~~

Snaps layer values to discrete boundaries.

Options:
    * ``--interval``: Stepping interval. Default: 10
    * ``--base``: Offset for the start of stepping. Default: 0


tileimage
~~~~~~~~~

Fetches tiles from an XYZ tile server and outputs a georeferenced image of whole
tiles.

Options:
    * ``--zoom``: Zoom level. Default: 13
    * ``--invert-y/--no-invert-y``: Invert the Y tile axis. Default: off
    * ``--delay``: Delay between requests. Default: 0
    * ``--concurrency``: Concurrent downloads. Default: 5
    * ``--tilesize``: Tile size in pixels. Default: 256
    * ``--raw``: Skip georeferencing. Default: off


tilesplit
~~~~~~~~~

Splits a single large DEM into smaller tiles.

Options:
    * ``--x-size``: Tile size in X. Default: 1000
    * ``--y-size``: Tile size in Y. Default: 1000
    * ``--x-offset``: Start offset in X. Default: 0
    * ``--y-offset``: Start offset in Y. Default: 0
    * ``--naming-scheme``: ``offset`` or ``letter``. Default: offset


zfit
~~~~

Re-scales the Z axis so values range from 0 to ``--fit``, shifting the model down
so its lowest point is the new zero. Use for standalone models, not tiles meant
to join.

Options:
    * ``--fit``: New target height. Default: 1
