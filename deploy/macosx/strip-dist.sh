#!/bin/sh
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/GDAL.framework/Versions/Current/libgdal.a
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/GDAL.framework/Versions/Current/Resources/doc
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/GDAL.framework/Versions/Current/Programs
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/PROJ.framework/Versions/Current/Programs
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/SQLite3.framework/Versions/Current/Programs
rm -Rf dist/MapMbTiles.app/Contents/Frameworks/UnixImageIO.framework/Versions/Current/Programs

rm -Rf dist/MapMbTiles.app/Contents/Resources/lib/python2.5/wx/tools

# Create versions for different architectures:
mkdir dist/i386
#ditto --rsrc --arch ppc dist/MapMbTiles.app dist/MapMbTiles-ppc.app
ditto --rsrc --arch i386 dist/MapMbTiles.app dist/i386/MapMbTiles.app
#lipo -thin i386 -output dist/i386/MapMbTiles.app/binary... dist/MapMbTiles.app/binary...
