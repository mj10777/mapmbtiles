import py2app
from setuptools import setup

# Build the .app file
setup(
    options=dict(
        py2app=dict(
            iconfile='resources/mapmbtiles.icns',
            packages='wx',
            excludes='osgeo,PIL,numpy',
            #site_packages=True,
            #semi_standalone=True,
            resources=['resources/license/LICENSE.txt','mapmbtiles'],
            plist=dict(
                CFBundleName               = "MapMbTiles",
                CFBundleShortVersionString = "1.0.alpha2",     # must be in X.X.X format
                CFBundleGetInfoString      = "MapMbTiles 1.0 alpha2",
                CFBundleExecutable         = "MapMbTiles",
                CFBundleIdentifier         = "de.mj10777.mapmbtiles",
            ),
            frameworks=['PROJ.framework','GEOS.framework','SQLite3.framework','UnixImageIO.framework','GDAL.framework'],
        ),
    ),
    app=[ 'mapmbtiles.py' ]
)
