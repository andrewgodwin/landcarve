import os

from setuptools import find_packages, setup

# We use the README as the long_description
readme_path = os.path.join(os.path.dirname(__file__), "README.rst")
with open(readme_path) as fp:
    long_description = fp.read()

setup(
    name="landcarve",
    version="0.1",
    author="Andrew Godwin",
    author_email="andrew@aeracode.org",
    description="Django ASGI (HTTP/WebSocket) server",
    long_description=long_description,
    license="BSD",
    zip_safe=False,
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "gdal[numpy]~=3.6.0",
        "numpy~=1.16",
        "click~=7.0",
        "svgwrite~=1.4",
        "scikit-image~=0.16",
        "requests~=2.18",
        "simplification~=0.5",
        "laspy[lazrs]~=2.5.0",
        "trimesh~=4.4.1",
        "manifold3d~=2.5.1",
    ],
    entry_points={"console_scripts": ["landcarve = landcarve.cli:main"]},
)
