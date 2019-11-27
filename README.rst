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


decifit
~~~~~~~

Options:
    * ``--xy-steps``: Size to fit the raster within. Default: 1000

Takes an input raster and fits it within certain limits of X and Y,
so there's at most ``--xy-steps`` rows and columns. Does not touch Z/values.

It will *preserve aspect ratios* - non-square inputs are scaled to the size of
their longest edge.


fixnodata
~~~~~~~~~

Options:
    * ``--nodata``: NODATA boundary for input data. Default: 0

All the rest of the tools in the suite assume a NODATA value of -1000. If you
have source data that is not aligned, use this pipeline step to set anything
equal or lower to the value of ``--nodata`` you pass to the internal NODATA
value.


realise
~~~~~~~

Options:
    * ``--xy-scale``: Scale factor for STL model in x/y axes. Default: 1
    * ``--z-scale``: Scale factor for STL model in z axis. Default: 1
    * ``--minimum``: Level to cut off detail and assume as base of model. Default: 0
    * ``--base``: Thickness of the base below the bottom of the model. Default: 1
    * ``--simplify/--no-simplify``: If simplification should be run. Default: ``--simplify``
    * ``--solid/--not-solid``: If the model should be forced to a square tile with no holes. Default: ``--not-solid``

The ``realise`` step takes a heightmap and renders it out as an STL file.

By default, the STL will have a dimension matching that of the input grid in all
dimensions - so if your input is a 500x500 heightmap with values from 0 - 50,
the resulting STL will have a dimension of 500x500x50.

To scale this linearly, use ``--xy-scale`` and ``--z-scale``.

If all points on your model are above a certain elevation, use ``--minimum`` set
at that elevation to shift the whole model downwards. The value of minimum will
be what ends up at zero height on the model, on top of the base thickness. Any
features that are below the minimum (but that have data) will be rendered flat.

``--base`` sets the thickness of the base of the model in output units. It's
recommended you have a base as most forms of manufacturing will need one.

Simplification is run on the STL model to try and merge flat areas together; if
you don't want this, pass ``--no-simplify``. The resulting model will have a lot
more polygons, but you'll save the slow simplification step. The built-in
simplification is quite basic; you may want to run it through another program
and do a shape-preserving simplification if your model is too detailed to load
into a slicer/pathing tool.

By default, areas that are set as NODATA in your heightmap will not be rendered
with a base; this is to allow non-rectangular outputs from the model. If your
goal is a set of tiles, though, set ``--solid`` to ensure you get a base; this
will help make sure your output is perfectly square.


smooth
~~~~~~

Options:
    * ``--factor``: Smoothing factor. Default: 1

Smooths heightmap data to remove jagged heights caused by reflections or laser
errors. Only use if your data is not already cleaned up.

The higher the factor, the more the model is smoothed.


zfit
~~~~

Options:
    * ``--fit``: New target height. Default: 1

Re-scales the Z axis (value) data so that it ranges between 0 and the value
passed for ``--fit``. As well as scaling the Z axis, this also includes shifting
the whole model down so the lowest value is the new 0 (for data which is
entirely at elevation).

Models printed using this will not have the same Z scale as each other. Only
use this for models that are not meant to be joined together.
