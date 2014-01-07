import py2app
from setuptools import setup

# Build the .app file
setup(
    options=dict(
        py2app=dict(
            iconfile='resources/mapmbtiles.icns',
            excludes='wx,osgeo,PIL,numpy',
            semi_standalone='yes',
            use_pythonpath='yes',
            resources=['resources/license/LICENSE.txt','mapmbtiles'],
            plist=dict(
                CFBundleName               = "MapMbTiles",
                CFBundleShortVersionString = "1.0.alpha2",     # must be in X.X.X format
                CFBundleGetInfoString      = "MapMbTiles 1.0 alpha2",
                CFBundleExecutable         = "MapMbTiles",
                CFBundleIdentifier         = "de.mj10777.mapmbtiles",
            ),
        ),
    ),
    app=[ 'mapmbtiles.py' ]
)
