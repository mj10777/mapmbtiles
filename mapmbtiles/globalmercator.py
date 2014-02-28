#!/usr/bin/env python
# -*- coding: utf-8 -*-
#******************************************************************************
#  $Id: mbtiles.py 15748 2008-11-17 16:30:54Z Mark Johnson $
#
# Project:  Google Summer of Code 2007, 2008 (http://code.google.com/soc/)
# - adapted for mbtiles - 2014 Mark Johnson
# - these classes were moved from the original gdal2tiles.py to here that they would be assible from mbtiles.py
# Support:  BRGM (http://www.brgm.fr)
# Purpose:  Convert a raster into TMS (Tile Map Service) tiles in a directory.
#           - generate Google Earth metadata (KML SuperOverlay)
#           - generate simple HTML viewer based on Google Maps and OpenLayers
#           - support of global tiles (Spherical Mercator) for compatibility
#               with interactive web maps a la Google Maps
# Author:   Klokan Petr Pridal, klokan at klokan dot cz
# Web:      http://www.klokan.cz/projects/gdal2mbtiles/
# GUI:      https://github.com/mj10777/mapmbtiles
#
###############################################################################
# Copyright (c) 2008, Klokan Petr Pridal
# - adapted for mbtiles - 2014 Mark Johnson
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#******************************************************************************

import math
import operator
import logging
from gettext import gettext as _

logger = logging.getLogger(__name__)

MAXZOOMLEVEL = 32
DEG_TO_RAD = math.pi/180
RAD_TO_DEG = 180/math.pi
MAX_LATITUDE = 85.0511287798
EARTH_RADIUS = 6378137

def minmax (a,b,c):
 a = max(a,b)
 a = min(a,c)
 return a

class InvalidCoverageError(Exception):
 """ Raised when coverage bounds are invalid """
 pass

class GlobalMercator(object):
 """
 TMS Global Mercator Profile
 ---------------------------

 Functions necessary for generation of tiles in Spherical Mercator projection,
 EPSG:900913 (EPSG:gOOglE, Google Maps Global Mercator), EPSG:3785, OSGEO:41001.

 Such tiles are compatible with Google Maps, Microsoft Virtual Earth, Yahoo Maps,
 UK Ordnance Survey OpenSpace API, ...
 and you can overlay them on top of base maps of those web mapping applications.

 Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

 What coordinate conversions do we need for TMS Global Mercator tiles::

      LatLon      <->       Meters      <->     Pixels    <->       Tile

  WGS84 coordinates   Spherical Mercator  Pixels in pyramid  Tiles in pyramid
      lat/lon            XY in metres     XY pixels Z zoom      XYZ from TMS
     EPSG:4326           EPSG:900913
      .----.              ---------               --                TMS
     /      \     <->     |       |     <->     /----/    <->      Google
     \      /             |       |           /--------/          QuadTree
      -----               ---------         /------------/
    KML, public         WebMapService         Web Clients      TileMapService

 What is the coordinate extent of Earth in EPSG:900913?

   [-20037508.342789244, -20037508.342789244, 20037508.342789244, 20037508.342789244]
   Constant 20037508.342789244 comes from the circumference of the Earth in meters,
   which is 40 thousand kilometers, the coordinate origin is in the middle of extent.
      In fact you can calculate the constant as: 2 * math.pi * 6378137 / 2.0
   $ echo 180 85 | gdaltransform -s_srs EPSG:4326 -t_srs EPSG:900913
   Polar areas with abs(latitude) bigger then 85.05112878 are clipped off.

 What are zoom level constants (pixels/meter) for pyramid with EPSG:900913?

   whole region is on top of pyramid (zoom=0) covered by 256x256 pixels tile,
   every lower zoom level resolution is always divided by two
   initialResolution = 20037508.342789244 * 2 / 256 = 156543.03392804062

 What is the difference between TMS and Google Maps/QuadTree tile name convention?

   The tile raster itself is the same (equal extent, projection, pixel size),
   there is just different identification of the same raster tile.
   Tiles in TMS are counted from [0,0] in the bottom-left corner, id is XYZ.
   Google placed the origin [0,0] to the top-left corner, reference is XYZ.
   Microsoft is referencing tiles by a QuadTree name, defined on the website:
   http://msdn2.microsoft.com/en-us/library/bb259689.aspx

 The lat/lon coordinates are using WGS84 datum, yeh?

   Yes, all lat/lon we are mentioning should use WGS84 Geodetic Datum.
   Well, the web clients like Google Maps are projecting those coordinates by
   Spherical Mercator, so in fact lat/lon coordinates on sphere are treated as if
   the were on the WGS84 ellipsoid.

   From MSDN documentation:
   To simplify the calculations, we use the spherical form of projection, not
   the ellipsoidal form. Since the projection is used only for map display,
   and not for displaying numeric coordinates, we don't need the extra precision
   of an ellipsoidal projection. The spherical projection causes approximately
   0.33 percent scale distortion in the Y direction, which is not visually noticable.

 How do I create a raster in EPSG:900913 and convert coordinates with PROJ.4?

   You can use standard GIS tools like gdalwarp, cs2cs or gdaltransform.
   All of the tools supports -t_srs 'epsg:900913'.

   For other GIS programs check the exact definition of the projection:
   More info at http://spatialreference.org/ref/user/google-projection/
   The same projection is degined as EPSG:3785. WKT definition is in the official
   EPSG database.

   Proj4 Text:
     +proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0
     +k=1.0 +units=m +nadgrids=@null +no_defs

   Human readable WKT format of EPGS:900913:
      PROJCS["Google Maps Global Mercator",
          GEOGCS["WGS 84",
              DATUM["WGS_1984",
                  SPHEROID["WGS 84",6378137,298.2572235630016,
                      AUTHORITY["EPSG","7030"]],
                  AUTHORITY["EPSG","6326"]],
              PRIMEM["Greenwich",0],
              UNIT["degree",0.0174532925199433],
              AUTHORITY["EPSG","4326"]],
          PROJECTION["Mercator_1SP"],
          PARAMETER["central_meridian",0],
          PARAMETER["scale_factor",1],
          PARAMETER["false_easting",0],
          PARAMETER["false_northing",0],
          UNIT["metre",1,
              AUTHORITY["EPSG","9001"]]]
 """

 WSG84 = 'EPSG:4326'
 Spherical_Mercator  = 'EPSG:3857'

 def __init__(self, tms_osm=False,tileSize=256,levels = [0]):
  "Initialize the TMS Global Mercator pyramid"
  self.tileSize = tileSize
  self.tms_osm=tms_osm
  self.initialResolution = 2 * math.pi * 6378137 / self.tileSize
  # 156543.03392804062 for tileSize 256 pixels
  self.originShift = 2 * math.pi * 6378137 / 2.0
  # 20037508.342789244
  if levels:
   self.init_levels(levels)

 def LatLonToMeters(self, lat, lon ):
  "Converts given lat/lon in WGS84 Datum to XY in Spherical Mercator EPSG:900913"
  mx = lon * self.originShift / 180.0
  my = math.log( math.tan((90 + lat) * math.pi / 360.0 )) / (math.pi / 180.0)
  my = my * self.originShift / 180.0
  return mx, my

 def BoundsToMeters(self, tile_bounds ):
  "Converts given lat/lon Bounds in WGS84 Datum to XY in Spherical Mercator EPSG:900913 / 3857 / 3395"
  xmin,ymin,xmax,ymax=tile_bounds
  xmin,ymin=self.LatLonToMeters(ymin,xmin)
  xmax,ymax=self.LatLonToMeters(ymax,xmax)
  return (xmin,ymin,xmax,ymax)

 def MetersToLatLon(self, mx, my ):
  "Converts XY point from Spherical Mercator EPSG:900913 to lat/lon in WGS84 Datum"
  lon = (mx / self.originShift) * 180.0
  lat = (my / self.originShift) * 180.0
  lat = 180 / math.pi * (2 * math.atan( math.exp( lat * math.pi / 180.0)) - math.pi / 2.0)
  return lat, lon

 def PixelsToMeters(self, px, py, zoom):
  "Converts pixel coordinates in given zoom level of pyramid to EPSG:900913"
  res = self.Resolution( zoom )
  mx = px * res - self.originShift
  my = py * res - self.originShift
  return mx, my

 def MetersToPixels(self, mx, my, zoom):
  "Converts EPSG:900913 to pyramid pixel coordinates in given zoom level"
  res = self.Resolution( zoom )
  px = (mx + self.originShift) / res
  py = (my + self.originShift) / res
  return px, py

 def PixelsToTile(self, px, py):
  "Returns a tile covering region in given pixel coordinates"
  tx = int( math.ceil( px / float(self.tileSize) ) - 1 )
  ty_tms = int( math.ceil( py / float(self.tileSize) ) - 1 )
  return tx, ty_tms

 def PixelsToRaster(self, px, py, zoom):
  "Move the origin of pixel coordinates to top-left corner"
  mapSize = self.tileSize << zoom
  return px, mapSize - py

 def MetersToTile(self, mx, my, zoom):
  "Returns tile for given mercator coordinates"
  px, py = self.MetersToPixels( mx, my, zoom)
  return self.PixelsToTile( px, py)

 def TileBounds(self, tx, ty_tms, zoom):
  "Returns bounds of the given tile in EPSG:900913 coordinates"
  minx, miny = self.PixelsToMeters( tx*self.tileSize, ty_tms*self.tileSize, zoom )
  maxx, maxy = self.PixelsToMeters( (tx+1)*self.tileSize, (ty_tms+1)*self.tileSize, zoom )
  return ( minx, miny, maxx, maxy )

 def TileLatLonBounds(self, tx, ty_tms, zoom ):
  "Returns bounds of the given tile in latutude/longitude using WGS84 datum"
  bounds = self.TileBounds( tx, ty_tms, zoom)
  minLat, minLon = self.MetersToLatLon(bounds[0], bounds[1])
  maxLat, maxLon = self.MetersToLatLon(bounds[2], bounds[3])
  return ( minLat, minLon, maxLat, maxLon )

 def Resolution(self, zoom ):
  "Resolution (meters/pixel) for given zoom level (measured at Equator)"
  # return (2 * math.pi * 6378137) / (self.tileSize * 2**zoom)
  return self.initialResolution / (2**zoom)

 def ZoomForPixelSize(self, pixelSize ):
  "Maximal scaledown zoom of the pyramid closest to the pixelSize."
  for i in range(MAXZOOMLEVEL):
   if pixelSize > self.Resolution(i):
    if i!=0:
     return i-1
    else:
     return 0 # We don't want to scale up

 def GoogleTile(self, tx, ty_tms, zoom):
  "Converts TMS tile coordinates to Google Tile coordinates"
  # coordinate origin is moved from bottom-left to top-left corner of the extent
  return tx, (2**zoom - 1) - ty_tms

 def QuadTree(self, tx, ty_tms, zoom ):
  "Converts TMS tile coordinates to Microsoft QuadTree"
  quadKey = ""
  ty_osm = (2**zoom - 1) - ty_tms
  for i in range(zoom, 0, -1):
   digit = 0
   mask = 1 << (i-1)
   if (tx & mask) != 0:
    digit += 1
   if (ty_osm & mask) != 0:
    digit += 2
   quadKey += str(digit)
  return quadKey

 # needed Landez project functions
 def init_levels(self,levels = [0]):
  self.Bc = []
  self.Cc = []
  self.zc = []
  self.Ac = []
  if not levels:
   raise InvalidCoverageError(_("Wrong zoom levels."))
  self.levels = levels
  self.maxlevel = max(levels) + 1
  c = self.tileSize
  for d in range(self.maxlevel):
   e = c/2;
   self.Bc.append(c/360.0)
   self.Cc.append(c/(2 * math.pi))
   self.zc.append((e,e))
   self.Ac.append(c)
   c *= 2

 # from Landez project
 # https://github.com/makinacorpus/landez
 def project_pixels(self,ll,zoom):
  d = self.zc[zoom]
  e = round(d[0] + ll[0] * self.Bc[zoom])
  f = minmax(math.sin(DEG_TO_RAD * ll[1]),-0.9999,0.9999)
  g = round(d[1] + 0.5*log((1+f)/(1-f))*-self.Cc[zoom])
  return (e,g)

 # from Landez project
 # https://github.com/makinacorpus/landez
 def unproject_pixels(self,px,zoom):
  e = self.zc[zoom]
  f = (px[0] - e[0])/self.Bc[zoom]
  g = (px[1] - e[1])/-self.Cc[zoom]
  h = RAD_TO_DEG * ( 2 * math.atan(math.exp(g)) - 0.5 * math.pi)
  if not self.tms_osm:
   # return tms numbering
   h = - h
  return (f,h)

 def tile_at(self, zoom, position):
  """
  Returns a tuple of (z, x, y)
  """
  x, y = self.project_pixels(position, zoom)
  return (zoom, int(x/self.tileSize), int(y/self.tileSize))

 # from Landez project
 # https://github.com/makinacorpus/landez
 def tile_bbox(self, (z, x, y_tms)):
  """
  Returns the WGS84 bbox of the specified tile [tms notation] west/north/east/south
  """
  topleft = (x * self.tileSize, (y_tms + 1) * self.tileSize)
  bottomright = ((x + 1) * self.tileSize, y_tms * self.tileSize)
  wn = self.unproject_pixels(topleft, z)
  es = self.unproject_pixels(bottomright, z)
  return wn + es

 # from Landez project
 # https://github.com/makinacorpus/landez
 def project(self, (lng, lat)):
  """
  Returns the coordinates in meters from WGS84
  """
  x = lng * DEG_TO_RAD
  lat = max(min(MAX_LATITUDE, lat), -MAX_LATITUDE)
  y = lat * DEG_TO_RAD
  y = math.log(math.tan((math.pi / 4) + (y / 2)))
  return (x*EARTH_RADIUS, y*EARTH_RADIUS)

 # from Landez project
 # https://github.com/makinacorpus/landez
 def unproject(self, (x, y)):
  """
  Returns the coordinates from position in meters
  """
  lng = x/EARTH_RADIUS * RAD_TO_DEG
  lat = 2 * math.atan(math.exp(y/EARTH_RADIUS)) - math.pi/2 * RAD_TO_DEG
  return (lng, lat)

 # from Landez project
 # https://github.com/makinacorpus/landez
 # this return list from north to south and west to east and precise bounds
 def tileslist(self, bbox):
  if not self.levels:
   raise InvalidCoverageError(_("Wrong zoom levels. [init_levels called?]"))
  if len(bbox) != 4:
   raise InvalidCoverageError(_("Wrong format of bounding box."))
  xmin, ymin, xmax, ymax = bbox
  if abs(xmin) > 180 or abs(xmax) > 180 or abs(ymin) > 90 or abs(ymax) > 90:
   s_error="";
   if abs(xmin) > 180:
    s_error+="abs(xmin) (%d) > 180 ; " % abs(xmin)
   if abs(xmax) > 180:
    s_error+="abs(xmax) (%d) > 180 ; " % abs(xmax)
   if abs(ymin) > 90:
    s_error+="abs(ymin) (%d) > 90 ; " % abs(ymin)
   if abs(ymax) > 90:
    s_error+="abs(ymax) (%d) > 90 ; " % abs(ymax)
   raise InvalidCoverageError(_("-E-> Some coordinates exceed [-180,+180], [-90, 90]. [%s]" % (s_error)))
  if xmin >= xmax or ymin >= ymax:
   s_error="";
   if xmin >= xmax:
    s_error+="xmin(%f) >= xmax(%f) ; " % (xmin,xmax)
   if ymin >= ymax:
    s_error+="ymin(%f) >= ymax(%f) ; " % (ymin,ymax)
   raise InvalidCoverageError(_("-E-> Bounding box format is (xmin, ymin, xmax, ymax) [%s]" % (s_error)))
  ll0 = (xmin, ymax)  # left top
  ll1 = (xmax, ymin)  # right bottom
  l = []
  for z in self.levels:
   px0 = self.project_pixels(ll0,z)
   px1 = self.project_pixels(ll1,z)
   for x in range(int(px0[0]/self.tileSize),int(px1[0]/self.tileSize)+1):
    if (x < 0) or (x >= 2**z):
     continue
    for y in range(int(px0[1]/self.tileSize),int(px1[1]/self.tileSize)+1):
     if (y < 0) or (y >= 2**z):
      continue
     if not self.tms_osm:
      # return tms numbering
      y = ((2**z-1) - y)
     lng_min,lat_max,lng_max, lat_min=self.tile_bbox((z,x,y))
     # logger.info(_("Save resulting image xy'%s' - bounds[%s]") % ((x,y),(lng_min,lat_max,lng_max, lat_min)))
     if lng_max > xmax:
      xmax=lng_max
     if lng_min < xmin:
      xmin=lng_min
     if lat_max > ymax:
      ymax=lat_max
     if lat_min < ymin:
      ymin=lat_min
     l.append((z, x, y))
  tile_bounds=(xmin,ymin,xmax,ymax)
  return (l,tile_bounds)

 # from Landez project
 # https://github.com/makinacorpus/landez
 def project_pixels(self,ll,zoom):
  d = self.zc[zoom]
  e = round(d[0] + ll[0] * self.Bc[zoom])
  f = minmax(math.sin(DEG_TO_RAD * ll[1]),-0.9999,0.9999)
  g = round(d[1] + 0.5*math.log((1+f)/(1-f))*-self.Cc[zoom])
  return (e,g)

#---------------------

class GlobalGeodetic(object):
 """
 TMS Global Geodetic Profile
 ---------------------------

 Functions necessary for generation of global tiles in Plate Carre projection,
 EPSG:4326, "unprojected profile".

 Such tiles are compatible with Google Earth (as any other EPSG:4326 rasters)
 and you can overlay the tiles on top of OpenLayers base map.

 Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

 What coordinate conversions do we need for TMS Global Geodetic tiles?

   Global Geodetic tiles are using geodetic coordinates (latitude,longitude)
   directly as planar coordinates XY (it is also called Unprojected or Plate
   Carre). We need only scaling to pixel pyramid and cutting to tiles.
   Pyramid has on top level two tiles, so it is not square but rectangle.
   Area [-180,-90,180,90] is scaled to 512x256 pixels.
   TMS has coordinate origin (for pixels and tiles) in bottom-left corner.
   Rasters are in EPSG:4326 and therefore are compatible with Google Earth.

      LatLon      <->      Pixels      <->     Tiles

  WGS84 coordinates   Pixels in pyramid  Tiles in pyramid
      lat/lon         XY pixels Z zoom      XYZ from TMS
     EPSG:4326
      .----.                ----
     /      \     <->    /--------/    <->      TMS
     \      /         /--------------/
      -----        /--------------------/
    WMS, KML    Web Clients, Google Earth  TileMapService
 """

 def __init__(self, tileSize = 256):
  self.tileSize = tileSize

 def LatLonToPixels(self, lat, lon, zoom):
  "Converts lat/lon to pixel coordinates in given zoom of the EPSG:4326 pyramid"

  res = 180.0 / self.tileSize / 2**zoom
  px = (180 + lat) / res
  py = (90 + lon) / res
  return px, py

 def PixelsToTile(self, px, py):
  "Returns coordinates of the tile [tms] covering region in pixel coordinates"

  tx = int( math.ceil( px / float(self.tileSize) ) - 1 )
  ty_tms = int( math.ceil( py / float(self.tileSize) ) - 1 )
  return tx, ty_tms

 def LatLonToTile(self, lat, lon, zoom):
  "Returns the tile for zoom which covers given lat/lon coordinates"

  px, py = self.LatLonToPixels( lat, lon, zoom)
  return self.PixelsToTile(px,py)

 def Resolution(self, zoom ):
  "Resolution (arc/pixel) for given zoom level (measured at Equator)"

  return 180.0 / self.tileSize / 2**zoom
  #return 180 / float( 1 << (8+zoom) )

 def ZoomForPixelSize(self, pixelSize ):
  "Maximal scaledown zoom of the pyramid closest to the pixelSize."

  for i in range(MAXZOOMLEVEL):
   if pixelSize > self.Resolution(i):
    if i!=0:
     return i-1
    else:
     return 0 # We don't want to scale up

 def TileBounds(self, tx, ty_tms, zoom):
  "Returns bounds of the given tile [tms]"
  res = 180.0 / self.tileSize / 2**zoom
  return (
   tx*self.tileSize*res - 180,
   ty_tms*self.tileSize*res - 90,
   (tx+1)*self.tileSize*res - 180,
   (ty_tms+1)*self.tileSize*res - 90
  )

 def TileLatLonBounds(self, tx, ty_tms, zoom):
  "Returns bounds of the given tile [tms] in the SWNE form"
  b = self.TileBounds(tx, ty_tms, zoom)
  return (b[1],b[0],b[3],b[2])

#---------------------
# TODO: Finish Zoomify implemtentation!!!
class Zoomify(object):
 """
 Tiles compatible with the Zoomify viewer
 ----------------------------------------
 """

 def __init__(self, width, height, tilesize = 256, tileformat='jpg'):
  """Initialization of the Zoomify tile tree"""

  self.tilesize = tilesize
  self.tileformat = tileformat
  imagesize = (width, height)
  tiles = ( math.ceil( width / tilesize ), math.ceil( height / tilesize ) )

  # Size (in tiles) for each tier of pyramid.
  self.tierSizeInTiles = []
  self.tierSizeInTiles.push( tiles )

  # Image size in pixels for each pyramid tierself
  self.tierImageSize = []
  self.tierImageSize.append( imagesize );

  while (imagesize[0] > tilesize or imageSize[1] > tilesize ):
   imagesize = (math.floor( imagesize[0] / 2 ), math.floor( imagesize[1] / 2) )
   tiles = ( math.ceil( imagesize[0] / tilesize ), math.ceil( imagesize[1] / tilesize ) )
   self.tierSizeInTiles.append( tiles )
   self.tierImageSize.append( imagesize )

  self.tierSizeInTiles.reverse()
  self.tierImageSize.reverse()

  # Depth of the Zoomify pyramid, number of tiers (zoom levels)
  self.numberOfTiers = len(self.tierSizeInTiles)

  # Number of tiles up to the given tier of pyramid.
  self.tileCountUpToTier = []
  self.tileCountUpToTier[0] = 0
  for i in range(1, self.numberOfTiers+1):
   self.tileCountUpToTier.append(
    self.tierSizeInTiles[i-1][0] * self.tierSizeInTiles[i-1][1] + self.tileCountUpToTier[i-1]
   )

 def tilefilename(self, x, y, z):
  """Returns filename for tile with given coordinates"""

  tileIndex = x + y * self.tierSizeInTiles[z][0] + self.tileCountUpToTier[z]
  return os.path.join("TileGroup%.0f" % math.floor( tileIndex / 256 ),
   "%s-%s-%s.%s" % ( z, x, y, self.tileformat))
