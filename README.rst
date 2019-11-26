Landcarve
=========

A collection of tools for making 3D models and similar things out of GIS data.
Designed to be run as a pipeline, though the individual tools can be run too.


decifit
-------

::

    decifit [options] <input-file> <output-file>

Takes an input raster and fits it within certain limits of X, Y and Z,
both in terms of the limits and the number of steps.

Designed for fitting a GIS file into restrictions that allow it to be fed
into a 3D model creation program without resource overload.

It will *preserve aspect ratios* - non-square inputs are scaled to the size of
their longest edge.

Z scaling is optional, and shouldn't be used if you want matching scales
with other pieces, as it will always scale to the given Z height.

Input options:

* ``--xy-steps``: Number of steps to scale down to on the longest edge
* ``--z-scale``: The new value of the highest Z point. Lowest will be 0.
* ``--nodata``: NODATA value to ignore on input and use for output (default ``-1000``)


realise
-------

Takes a raster layer and makes a 3D model out of it. Respects NODATA sections
to make non-square outputs.

