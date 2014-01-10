#!/usr/bin/env python
#******************************************************************************
#  $Id: mbtiles.py 15748 2008-11-17 16:30:54Z Mark Johnson $
#
# Project:  Google Summer of Code 2007, 2008 (http://code.google.com/soc/)
# - adapted for mbtiles - 2014 Mark Johnson
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

from osgeo import gdal
from osgeo import osr

import collections
import json
import logging
import mimetypes
import math
import operator
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from gettext import gettext as _

from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from io import BytesIO

from globalmercator import GlobalMercator

has_pil = False

try:
 from PIL import Image, ImageEnhance
 has_pil = True
 import numpy
 from xml.etree import ElementTree
 import osgeo.gdal_array as gdalarray
except:
 # 'antialias' resampling is not available
 pass


""" Default tiles URL """
DEFAULT_TILES_URL = "http://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
""" Default tiles subdomains """
DEFAULT_TILES_SUBDOMAINS = list("abc")
""" Base temporary folder """
DEFAULT_TMP_DIR = os.path.join(tempfile.gettempdir(), 'mapmbtiles')
""" Default output MBTiles file """
DEFAULT_MBTILES_OUTPUT = os.path.join(os.getcwd(), "mbtiles_output.mbtiles")
""" Default tile size in pixels (*useless* in remote rendering) """
DEFAULT_TILE_SIZE = 256
""" Default tile format (mime-type) """
DEFAULT_TILE_FORMAT = 'image/jpg'
""" Number of retries for remove tiles downloading """
DOWNLOAD_RETRIES = 10
""" Path to fonts for Mapnik rendering """
TRUETYPE_FONTS_PATH = '/usr/share/fonts/truetype/'

logger = logging.getLogger(__name__)

# =============================================================================
# UPDATE map SET tile_id = replace(tile_id, '.None', '.tms');
# UPDATE images SET tile_id = replace(tile_id, '.None', '.tms');
# =============================================================================
# base on code faound at. https://github.com/mapbox/mbutil/blob/master/mbutil/util.py
# - creation of mbtiles based on logic used in the geopaparazzi project
# - functions added to be used by gdalt2tiles.py [gdal2mbtiles.py]
# =============================================================================
class MbTiles(object):
 def __init__(self):
  self.verbose=False
  self.s_y_type="tms"
  tms_osm=False
  self.tilesize=256
  self.bounds_west=-180.0
  self.bounds_east=180.0
  self.bounds_north=85.05113
  self.bounds_south=-85.05113
  self.min_zoom=0
  self.max_zoom=22
  self.default_zoom=1
  self.mbtiles_name=""
  self.mbtiles_description=""
  self.mbtiles_type="baselayer"
  self.mbtiles_version='1.1'
  self.s_y_type = 'tms'
  self.tms_osm=False
  self.mbtiles_format='jpg'
  self.mbtiles_minzoom='0'
  self.mbtiles_maxzoom='22'
  self.mbtiles_bounds="%f,%f,%f,%f"% (self.bounds_west,self.bounds_south,self.bounds_east,self.bounds_north)
  self.center_x=(self.bounds_east+self.bounds_west)/2
  self.center_y=(self.bounds_north+self.bounds_south)/2
  self.mbtiles_center="%f,%f,%s"%(self.center_x,self.center_y,self.default_zoom)

 def open_db(self,s_path_db,mbtiles_dir,mbtiles_format,s_y_type,verbose=False):
  self.s_path_db = s_path_db
  self.mbtiles_dir=mbtiles_dir.strip()
  if self.mbtiles_dir == "":
   self.mbtiles_dir=os.path.dirname(self.mbtiles_file)+ '/'
  if s_y_type == "osm":
   self.s_y_type=s_y_type
   self.tms_osm=True
  self.mbtiles_format=mbtiles_format
  self.verbose=verbose
  # self.verbose=True
  # setting a default value
  self.mbtiles_name=os.path.splitext(os.path.basename( self.s_path_db ))[0]
  self.mbtiles_description=self.mbtiles_name.replace("."," ")
  self.mbtiles_description=self.mbtiles_description.replace("_"," ")
  db_create=os.path.exists(self.s_path_db)
  self.sqlite3_connection=self.mbtiles_connect(s_path_db)
  self.mbtiles_cursor = self.sqlite3_connection.cursor()
  # self.optimize_connection()
  if not db_create:
   if self.verbose:
    print "MbTiles[",db_create,"] : creating [",self.s_path_db,"] "
   self.mbtiles_create()
  else:
   if self.verbose:
    print "MbTiles[",db_create,"] : opening [",self.s_path_db,"] "
   self.fetch_metadata()

 def close_db(self):
  if self.verbose:
   print "MbTiles[close_db] : closing [",self.s_path_db,"] "
  if self.mbtiles_cursor:
   self.mbtiles_cursor.close()
  if self.sqlite3_connection:
   self.sqlite3_connection.close()
   if os.path.exists("%s-journal" % self.s_path_db):
    os.remove("%s-journal" % self.s_path_db)

 def flip_y(self,zoom, y):
  # z=19: y[ 352336 ]  y_osm[ 171951 ]  y_tms[ 352336 ]
  # SELECT  CastToInteger(pow(2,19) - 1 - 352336) 'y_osm',CastToInteger(pow(2,19) - 1 - 171951) 'y_tms';
  return (2**zoom-1) - y

 def mbtiles_create(self):
  self.mbtiles_cursor.execute("""CREATE TABLE android_metadata (locale text);""")
  self.mbtiles_cursor.execute("""CREATE TABLE metadata (name text, value text);""")
  self.mbtiles_cursor.execute("""CREATE TABLE grid_key (grid_id TEXT,key_name TEXT);""")
  self.mbtiles_cursor.execute("""CREATE TABLE grid_utfgrid (grid_id TEXT,grid_utfgrid BLOB);""")
  self.mbtiles_cursor.execute("""CREATE TABLE keymap (key_name TEXT,key_json TEXT);""")
  self.mbtiles_cursor.execute("""CREATE TABLE images (tile_data blob,tile_id text);""")
  self.mbtiles_cursor.execute("""CREATE TABLE map (zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_id TEXT,grid_id TEXT);""")
  self.mbtiles_cursor.execute("""CREATE VIEW tiles AS SELECT map.zoom_level AS zoom_level,map.tile_column AS tile_column,map.tile_row AS tile_row,images.tile_data AS tile_data FROM map JOIN images ON images.tile_id = map.tile_id ORDER BY zoom_level,tile_column,tile_row;""")
  self.mbtiles_cursor.execute("""CREATE VIEW grids AS SELECT map.zoom_level AS zoom_level,map.tile_column AS tile_column,map.tile_row AS tile_row,grid_utfgrid.grid_utfgrid AS grid FROM map JOIN grid_utfgrid ON grid_utfgrid.grid_id = map.grid_id;""")
  self.mbtiles_cursor.execute("""CREATE VIEW grid_data AS SELECT map.zoom_level AS zoom_level,map.tile_column AS tile_column,map.tile_row AS tile_row,keymap.key_name AS key_name,keymap.key_json AS key_json FROM map JOIN grid_key ON map.grid_id = grid_key.grid_id JOIN keymap ON grid_key.key_name = keymap.key_name;""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX name ON metadata (name);""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX grid_key_lookup ON grid_key (grid_id,key_name);""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX grid_utfgrid_lookup ON grid_utfgrid (grid_id);""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX keymap_lookup ON keymap (key_name);""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX images_id ON images (tile_id);""")
  self.mbtiles_cursor.execute("""CREATE UNIQUE INDEX map_index ON map (zoom_level, tile_column, tile_row);""")

 def mbtiles_connect(self,mbtiles_file):
  try:
   con = sqlite3.connect(mbtiles_file)
   return con
  except Exception, e:
   logger.error("Could not connect to database")
   logger.exception(e)
   sys.exit(1)

 def fetch_metadata(self):
  self.metadata_return=self.mbtiles_cursor.execute('SELECT LOWER(name), value FROM metadata;').fetchall()
  self.metadata=dict(self.metadata_return)
  if self.metadata:
   self.mbtiles_name=self.metadata.get('name',self.mbtiles_name)
   self.mbtiles_description=self.metadata.get('description',self.mbtiles_description)
   self.mbtiles_type=self.metadata.get('type',self.mbtiles_type)
   self.mbtiles_version=self.metadata.get('version',self.mbtiles_version)
   self.s_y_type = self.metadata.get('tile_row_type',self.s_y_type)
   self.mbtiles_format=self.metadata.get('format',self.mbtiles_format)
   self.mbtiles_bounds=self.metadata.get('bounds',self.mbtiles_bounds)
   sa_bounds=self.mbtiles_bounds.split(",")
   if len(sa_bounds) == 4:
    self.bounds_west=float(sa_bounds[0])
    self.bounds_east=float(sa_bounds[2])
    self.bounds_north=float(sa_bounds[3])
    self.bounds_south=float(sa_bounds[1])
   self.mbtiles_minzoom=self.metadata.get('minzoom',self.mbtiles_minzoom)
   self.mbtiles_maxzoom=self.metadata.get('maxzoom',self.mbtiles_maxzoom)
   self.center_x=(self.bounds_east+self.bounds_west)/2
   self.center_y=(self.bounds_north+self.bounds_south)/2
   self.mbtiles_center="%f,%f,%s"%(self.center_x,self.center_y,self.mbtiles_minzoom)
   self.mbtiles_center=self.metadata.get('center',self.mbtiles_center)
   sa_center=self.mbtiles_center.split(",")
   if len(sa_center) == 3:
    self.center_x=float(sa_center[0])
    self.center_y=float(sa_center[1])
    self.default_zoom=int(sa_center[2])
  return self.metadata_return

 def optimize_connection(self):
  self.mbtiles_cursor.execute("""PRAGMA synchronous=0""")
  self.mbtiles_cursor.execute("""PRAGMA locking_mode=EXCLUSIVE""")
  self.mbtiles_cursor.execute("""PRAGMA journal_mode=DELETE""")

 def optimize_database(self):
  if self.verbose:
   print "MbTiles : ioptimize_database: analyzing db"
  self.mbtiles_cursor.execute("""ANALYZE;""")
  if self.verbose:
   print "MbTiles : optimize_database: cleaning db"
  self.mbtiles_cursor.execute("""VACUUM;""")
  if self.verbose:
   print "MbTiles : optimize_database: [",self.s_path_db,"]"

 def insert_metadata(self,metadata_list):
  if metadata_list:
   if self.verbose:
    print "MbTiles : insert_metadata:",metadata_list
   try:
    self.mbtiles_cursor.executemany("INSERT OR REPLACE INTO metadata VALUES(?,?)",metadata_list)
    self.sqlite3_connection.commit()
   except sqlite3.Error, e:
    self.sqlite3_connection.rollback()
    print "MbTiles : insert_metadata: Error %s:" % e.args[0]
   self.fetch_metadata()

 def save_metadata(self):
  if not self.s_y_type:
   self.s_y_type="tms"
  values_list = [
         ('name', self.mbtiles_name),
         ('description',self.mbtiles_description ),
         ('type', self.mbtiles_type),
         ('version', self.mbtiles_version),
         ('tile_row_type',self.s_y_type),
         ('format', self.mbtiles_format),
         ('bounds', self.mbtiles_bounds),
         ('center', self.mbtiles_center),
         ('minzoom', self.mbtiles_minzoom),
         ('maxzoom', self.mbtiles_maxzoom)
        ]
  self.insert_metadata(values_list)

 def insert_image(self,tz,tx,ty,image_data):
  if not self.s_y_type:
   self.s_y_type="tms"
  if not self.mbtiles_cursor:
   self.mbtiles_cursor = self.sqlite3_connection.cursor()
  s_tile_id="{0}-{1}-{2}.{3}".format(str(tz), str(tx),str(ty),self.s_y_type)
  s_tile_id=self.check_image(s_tile_id,image_data)
  sql_insert_map="INSERT OR REPLACE INTO map (tile_id,zoom_level,tile_column,tile_row,grid_id) VALUES(?,?,?,?,?);";
  map_values = [(s_tile_id,tz,tx,ty,'')]
  sql_insert_image="INSERT OR REPLACE INTO images (tile_id,tile_data) VALUES(?,?);"
  image_values = [(s_tile_id,buffer(image_data))]
  # sqlite3.Binary(image_data)
  if self.verbose:
   print "MbTiles : insert_image: ",tz,tx,ty," id[",s_tile_id,"]"
  try:
   self.mbtiles_cursor.executemany(sql_insert_map,map_values)
   self.mbtiles_cursor.executemany(sql_insert_image,image_values)
   self.sqlite3_connection.commit()
  except sqlite3.Error, e:
   self.sqlite3_connection.rollback()
   print "MbTiles : insert_image: Error %s:" % e.args[0]

 def check_image(self,s_tile_id,image_data):
  # a list of (count, color) tuples or None, max amount [we only want information about a blank image]
  colors = Image.open(BytesIO(image_data)).getcolors(1)
   # TypeError: 'buffer' does not have the buffer interface
  if colors:
   # MbTiles : check_image: tile_id[ 18-140789-176144.tms ] colors[ [(65536, (255, 255, 255, 255))] ]
   # color_values[ (65536, (255, 255, 255, 255)) ]
   color_values=colors[0]
   # rgb_values[ (255, 255, 255, 255) ]
   rgb_values=color_values[1]
   # r[ 255 ] g[ 255 ] b[ 255 ]
   r_value=rgb_values[0]
   g_value=rgb_values[1]
   b_value=rgb_values[2]
   s_tile_orig = s_tile_id
   # exception because of hex, avoid this type of formatting - use .format(..)
   s_tile_id = "%2x-%2x-%2x.rgb"%(int(r_value),int(g_value),int(b_value))
   # print "MbTiles : check_image: tile_id[",s_tile_orig,";",s_tile_id,"] colors[",colors,"] color_values[",color_values,"] rgb_values[",rgb_values,"] r[",r_value,"] g[",g_value,"] b[",b_value,"]"
   # MbTiles : check_image: [(65536, (255, 255, 255))] 18-140785-176149.tms
   # colors = len(filter(None,image_img.histogram()))
  return s_tile_id

 def retrieve_blank_image(self,r,g,b):
  s_tile_id="{0}-{1}-{2}.{3}".format(str(r), str(g),str(b),"rgb")
  tile_id = (s_tile_id,)
  self.mbtiles_cursor.execute("SELECT tile_data FROM images WHERE tile_id = ?",tile_id)
  image_data = self.mbtiles_cursor.fetchone()
  if image_data is None:
   image = Image.new("RGB", (self.tilesize, self.tilesize), (r, g, b))
   s_tile_id="{0}-{1}-{2}.{3}".format(str(r), str(g),str(b),self.mbtiles_format)
   image.save(s_tile_id)
   input_file = open(s_tile_id, 'rb')
   if not input_file.closed:
    image_file = input_file.read()
    input_file.close()
    image_data = (image_file,)
    os.remove(s_tile_id)
  return image_data

 def retrieve_bounds(self):
  min_zoom=22
  max_zoom=0
  bounds_west=180.0
  bounds_east=-180.0
  bounds_north=-85.05113
  bounds_south=85.05113
  if not self.mbtiles_cursor:
   self.mbtiles_cursor = self.sqlite3_connection.cursor()
  mercator = GlobalMercator(self.tms_osm)
  zoom_levels = self.mbtiles_cursor.execute('SELECT DISTINCT(zoom_level) FROM map ORDER BY zoom_level;').fetchall()
  for i in range(len(zoom_levels)):
   i_zoom = int(zoom_levels[i][0])
   if i_zoom > max_zoom:
    max_zoom=i_zoom
   if i_zoom < min_zoom:
    min_zoom=i_zoom
   zoom_id = (str(i_zoom),)
   bounds_minmax = self.mbtiles_cursor.execute('SELECT min(tile_column),min(tile_row),max(tile_column),max(tile_row) FROM map WHERE (zoom_level = ?);',zoom_id).fetchone()
   i_x_min = int(bounds_minmax[0])
   i_y_min = int(bounds_minmax[1])
   i_x_max = int(bounds_minmax[2])
   i_y_max = int(bounds_minmax[3])
   # print "MbTiles : retrieve_bounds: i_zoom %d min(%d,%d) ; max(%d,%d)" % (i_zoom,i_x_min,i_y_min,i_x_max,i_y_max)
   tile_bounds= mercator.TileLatLonBounds(i_x_min,i_y_min,i_zoom)
   if tile_bounds[0] < bounds_south:
    bounds_south=tile_bounds[0]
   if tile_bounds[1] < bounds_west:
    bounds_west=tile_bounds[1]
   tile_bounds= mercator.TileLatLonBounds(i_x_max,i_y_max,i_zoom)
   if tile_bounds[2] > bounds_north:
    bounds_north=tile_bounds[2]
   if tile_bounds[3] > bounds_east:
    bounds_east=tile_bounds[3]
  self.mbtiles_bounds="%f,%f,%f,%f"% (bounds_west,bounds_south,bounds_east,bounds_north)
  mbtiles_center_x=(bounds_east+bounds_west)/2
  mbtiles_center_y=(bounds_north+bounds_south)/2
  self.mbtiles_center="%f,%f,%s"%(mbtiles_center_x,mbtiles_center_y,min_zoom)
  self.mbtiles_minzoom=min_zoom
  self.mbtiles_maxzoom=max_zoom
  self.save_metadata()
  self.optimize_database()

 def retrieve_image(self,tz,tx,ty):
  if not self.s_y_type:
   self.s_y_type="tms"
  if not self.mbtiles_cursor:
   self.mbtiles_cursor = self.sqlite3_connection.cursor()
  tile_zxy = (str(tz), str(tx),str(ty))
  # SELECT tile_data FROM tiles WHERE ((zoom_level = 1) AND (tile_column = 1) AND (tile_row = 1))
  self.mbtiles_cursor.execute("SELECT tile_data FROM tiles WHERE ((zoom_level = ?) AND (tile_column = ?) AND (tile_row = ?))",tile_zxy)
  image_data = self.mbtiles_cursor.fetchone()
  if image_data is None:
   return  None
  return bytes(image_data[0])

 def retrieve_zoom_images(self,tz,tx,ty):
  if not self.s_y_type:
   self.s_y_type="tms"
  if not self.mbtiles_cursor:
   self.mbtiles_cursor = self.sqlite3_connection.cursor()
  s_tile_source="{0}-{1}-{2}.{3}".format(str(tz), str(tx),str(ty),self.s_y_type)
  tz=tz+1
  image_list = list() # empty list
  for y in range(2*ty,2*ty + 2):
   for x in range(2*tx, 2*tx + 2):
    s_tile_id="{0}-{1}-{2}.{3}".format(str(tz), str(x),str(y),self.s_y_type)
    s_file_id="{0}{1}-{2}-{3}.{4}".format(self.mbtiles_dir,str(tz), str(x),str(y),self.mbtiles_format)
    tile_id = (s_tile_id,)
    self.mbtiles_cursor.execute("SELECT tile_data FROM images WHERE tile_id = ?",tile_id)
    image_data = self.mbtiles_cursor.fetchone()
    if self.verbose:
     print "MbTiles : retrieve_zoom_images: source[",s_tile_source,"] : fetching[",s_tile_id,"] "
    if image_data is None:
     # 1 / 8051 /media/gb_1500/maps/geo_tiff/rd_Berlin_Schmettau/18-140798-176204.jpg
     # [19-281597-352408.jpg] istilie_id '0-0-0.rgb'
     s_tile_id_orig=s_tile_id
     s_tile_id=self.count_tiles(tz,x,y,10)
     if self.verbose:
      print "MbTiles : retrieve_zoom_images: fetching[",s_tile_id_orig,"] failed ; may be a rgb-image ; attempting [",s_tile_id,"]"
     tile_id = (s_tile_id,)
     self.mbtiles_cursor.execute("SELECT tile_data FROM images WHERE tile_id = ?",tile_id)
     image_data = self.mbtiles_cursor.fetchone()
     if image_data is None:
      # retireve an blank image fromdatabase, if does not exist, create it
      image_data = self.retrieve_blank_image(0,0,0)
    if image_data:
     output_file = open(s_file_id, 'wb')
     if not output_file.closed:
      output_file.write(image_data[0])
      output_file.close()
      image_list.append(s_file_id)
  return image_list

 def count_tiles(self,tz,tx,ty,i_parm):
  # even when empty, 0 will be returned
  if not self.s_y_type:
   self.s_y_type="tms"
  if not self.mbtiles_cursor:
   self.mbtiles_cursor = self.sqlite3_connection.cursor()
  if i_parm == 10:
   s_sql_command="SELECT tile_id FROM map WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?"
   tile_id = (str(tz),str(tx),str(ty))
  if i_parm == 0:
   s_tile_id="{0}-{1}-{2}.{3}".format(str(tz), str(tx),str(ty),self.s_y_type)
   s_sql_command="SELECT count(tile_id) FROM map WHERE tile_id = ?"
   tile_id = (s_tile_id,)
  elif i_parm < 4:
   if i_parm == 1:
    # '%-%-%.%' : all tiles
    s_tile_id="%-%-%.%"
    s_sql_command="SELECT count(tile_id) FROM map WHERE tile_id LIKE ?"
   if i_parm == 2:
    # '15-%-%.%' all tiles of z ; Note: there may be .rgb entries
    s_tile_id="{0}".format(str(tz))
    s_sql_command="SELECT count(tile_id)  FROM map WHERE zoom_level = ?"
   if i_parm == 3:
    # '%-17600-%.%' all tiles of x ; Note: there may be .rgb entries
    s_tile_id="{0}".format(str(tx))
    s_sql_command="SELECT count(tile_id)  FROM map WHERE tile_column = ?"
   tile_id = (s_tile_id,)
  self.mbtiles_cursor.execute(s_sql_command,tile_id)
  i_count = self.mbtiles_cursor.fetchone()
  if i_count is None:
   if i_parm == 10:
    s_tile_id="{0}-{1}-{2}.{3}".format(str(0), str(0),str(0),"rgb")
    i_count = (s_tile_id,)
   else:
    i_count = (0,)
  return i_count[0]

 def get_tile_dirs(self,path):
  return [name for name in os.listdir(path) if os.path.isdir(os.path.join(path, name))]

 def mbtiles_from_disk(self,directory_path):
  if not os.path.exists(directory_path):
   print "MbTiles : mbtiles_from_disk: directory does not exist : [",directory_path,"] "
  print "MbTiles : mbtiles_from_disk: fetching[",directory_path,"] "
  image_format = ""
  min_zoom=22
  max_zoom=0
  bounds_west=180.0
  bounds_east=-180.0
  bounds_north=-85.05113
  bounds_south=85.05113
  mercator = GlobalMercator(self.tms_osm)
  if self.mbtiles_description == '':
   self.mbtiles_description=os.path.splitext(os.path.basename(directory_path))[0]
   if self.mbtiles_name == '':
    self.mbtiles_name=self.mbtiles_description.replace("."," ")
    self.mbtiles_name=self.mbtiles_name.replace("_"," ")
  for zoomDir in self.get_tile_dirs(directory_path):
   z = int(zoomDir)
   if z > max_zoom:
    max_zoom=z
   if z < min_zoom:
    min_zoom=z
   for rowDir in self.get_tile_dirs(os.path.join(directory_path, zoomDir)):
    x = int(rowDir)
    for current_file in os.listdir(os.path.join(directory_path, zoomDir, rowDir)):
     file_name, ext = current_file.split('.', 1)
     if image_format == "":
      image_format=ext
     f = open(os.path.join(directory_path, zoomDir, rowDir, current_file), 'rb')
     image_data = f.read()
     f.close()
     y = int(file_name)
     self.insert_image(z,x,y,image_data)
     tile_bounds= mercator.TileLatLonBounds(x,y,z)
     if tile_bounds[0] < bounds_south:
      bounds_south=tile_bounds[0]
     if tile_bounds[1] < bounds_west:
      bounds_west=tile_bounds[1]
     if tile_bounds[2] > bounds_north:
      bounds_north=tile_bounds[2]
     if tile_bounds[3] > bounds_east:
      bounds_east=tile_bounds[3]

  self.mbtiles_format=image_format
  self.mbtiles_bounds="%f,%f,%f,%f"% (bounds_west,bounds_south,bounds_east,bounds_north)
  mbtiles_center_x=(bounds_east+bounds_west)/2
  mbtiles_center_y=(bounds_north+bounds_south)/2
  self.mbtiles_center="%f,%f,%s"%(mbtiles_center_x,mbtiles_center_y,min_zoom)
  self.mbtiles_minzoom=min_zoom
  self.mbtiles_maxzoom=max_zoom
  self.save_metadata()
  self.optimize_database()
  if not  os.path.exists(os.path.join(directory_path, "tilemapresource.xml")):
   s_xml=self.mbtiles_create_tilemapresource();
   f = open(os.path.join(directory_path, "tilemapresource.xml"), 'w')
   f.write(s_xml)
   f.close()
  if self.verbose:
   print "MbTiles : mbtiles_from_disk: [",self.s_path_db,"] - Habe fertig"

 def mbtiles_to_disk(self,directory_path):
  print "MbTiles : mbtiles_to_disk: reading [",self.s_path_db,"]]"
  if not os.path.exists(directory_path):
   os.mkdir("%s" % directory_path)
  count = self.mbtiles_cursor.execute('SELECT count(zoom_level) FROM tiles;').fetchone()[0]
  tiles = self.mbtiles_cursor.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles;')
  t = tiles.fetchone()
  while t:
   z = t[0]
   x = t[1]
   y = t[2]
   tile_dir = os.path.join(directory_path, str(z), str(x))
   if not os.path.isdir(tile_dir):
    os.makedirs(tile_dir)
   tile = os.path.join(tile_dir,'%s.%s' % (y, self.mbtiles_format))
   f = open(tile, 'wb')
   f.write(t[3])
   f.close()
   t = tiles.fetchone()
  s_xml=self.mbtiles_create_tilemapresource();
  f = open(os.path.join(directory_path, "tilemapresource.xml"), 'w')
  f.write(s_xml)
  f.close()
  if self.verbose:
   print "MbTiles : mbtiles_to_disk: created directory[",directory_path,"] with ",count," tiles - Habe fertig"

 # -------------------------------------------------------------------------
 # http://docs.python.org/2/library/xml.etree.elementtree.html
 def mbtiles_read_tilemapresource(self,s_xml_file):
  tile_map = ElementTree.parse(s_xml_file).getroot()
  if tile_map:
   min_zoom=22
   max_zoom=0
   default_zoom=-1
   s_tile_row_type=""
   if tile_map.tag == 'TileMap':
    tile_srs = tile_map.find('SRS')
    if tile_srs:
     if tile_srs.text != 'EPSG:900913':
      # we support only mercator, assume invalid and return
      return
    tile_format = tile_map.find('TileFormat')
    if tile_format:
     tile_format_width = tile_format.get('width')
     tile_format_height = tile_format.get('height')
     if tile_format_width != "256" or tile_format_height != "256":
      # we support tiles of a size of 256, assume invalid and return
      return
     tile_format_mime = tile_format.get('mime-type')
     if tile_format_mime == "image/png" or tile_format_mime == "image/jpeg":
      self.mbtiles_format = tile_format.get('extension')
     else:
      # we support only jpg or png files, assume invalid and return
      return
     tile_format_tile_row_type = tile_format.get('tile_row_type')
     if tile_format_tile_row_type:
      # this is an unofficial parameter
      if tile_format_tile_row_type != "" and tile_format_tile_row_type != "tms":
       if tile_format_tile_row_type == "osm":
        # 'tms' is default - only to reset of osm
        s_tile_row_type=tile_format_tile_row_type
    tile_sets = tile_map.find('TileSets')
    if tile_sets:
     tile_sets_profile = tile_sets.get('profile')
     if tile_sets_profile != 'mercator':
      # we support only mercator, assume invalid and return
      return
     else:
      for zoom_level in tile_sets.getiterator('TileSet'):
       i_zoom = int(zoom_level.get("order"))
       if i_zoom > max_zoom:
        max_zoom=i_zoom
       if i_zoom < mim_zoom:
        min_zoom=i_zoom
      if min_zoom >= 0 and min_zoom <= 22 and max_zoom >= 0 and max_zoom <= 22:
       if min_zoom > max_zoom:
        i_zoom=max_zoom
        max_zoom=min_zoom
        min_zoom=i_zoom
       self.mbtiles_minzoom=min_zoom
       self.mbtiles_maxzoom=max_zoom
      else:
       return
    tile_title = tile_map.find('Title')
    if tile_title:
     self.mbtiles_name=tile_title.text
    tile_description = tile_map.find('Abstract')
    if tile_description:
     self.mbtiles_description=tile_description.text
    tile_origin = tile_map.find('Origin')
    if tile_origin:
     tile_origin_default_z = tile_origin.get('default_z')
     tile_origin_x = tile_origin.get('x')
     tile_origin_y = tile_origin.get('y')
     center_x=float(tile_origin_x)
     center_y=float(tile_origin_y)
     if tile_origin_default_z:
      # this is an unofficial parameter: Original will be interpeded as center of intrest with a default zoom
      default_zoom=int(tile_origin_default_z)
    tile_boundingbox = tile_map.find('BoundingBox')
    if tile_boundingbox:
     tile_minx = tile_boundingbox.get('minx')
     tile_miny = tile_boundingbox.get('miny')
     tile_maxx = tile_boundingbox.get('maxx')
     tile_maxy = tile_boundingbox.get('maxy')
     if default_zoom >= 0:
      self.mbtiles_bounds="%f,%f,%f,%f"% (float(tile_minx),float(tile_miny),float(tile_maxx),float(tile_maxy))
      self.mbtiles_center="%f,%f,%s"%(center_x,center_y,default_zoom)
     else:
      if tile_minx == tile_origin_x and tile_maxy == tile_origin_y:
       self.mbtiles_bounds="%f,%f,%f,%f"% (float(tile_minx),float(tile_miny),float(tile_maxx),float(tile_maxy))
       mbtiles_center_x=(float(tile_maxx)+float(tile_minx))/2
       mbtiles_center_y=(float(tile_maxy)+float(tile_miny))/2
       self.mbtiles_center="%f,%f,%s"%(mbtiles_center_x,mbtiles_center_y,min_zoom)

 # -------------------------------------------------------------------------
 def mbtiles_create_tilemapresource(self):
  """
     Template for tilemapresource.xml. Returns filled string. Expected variables:
       title, north, south, east, west, isepsg4326, projection, publishurl,
       zoompixels, tilesize, tileformat, profile
       http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification
  """
  args = {}
  args['title'] = self.mbtiles_name
  args['description'] = self.mbtiles_description
  args['south'] = self.bounds_south
  args['west'] = self.bounds_west
  args['north'] = self.bounds_north
  args['east'] = self.bounds_east
  args['center_x'] = self.center_x
  args['center_y'] = self.center_y
  args['default_z'] = self.default_zoom
  args['tilesize'] = self.tilesize
  args['tileformat'] = self.mbtiles_format
  s_mime=self.mbtiles_format
  if s_mime == "jpg":
   s_mime="jpeg"
  args['mime'] = "{0}/{1}".format("image",s_mime)
  args['publishurl'] = ""
  args['profile'] = "mercator"
  args['srs'] = "EPSG:900913"
  args['tile_row_type'] =self.s_y_type
  args['default_zoom'] =self.s_y_type

  s_xml = """<?xml version="1.0" encoding="utf-8"?>
<TileMap version="1.0.0" tilemapservice="http://tms.osgeo.org/1.0.0">
 <Title>%(title)s</Title>
 <Abstract>%(description)s</Abstract>
 <SRS>%(srs)s</SRS>
 <BoundingBox minx="%(west).14f" miny="%(south).14f" maxx="%(east).14f" maxy="%(north).14f"/>
 <Origin x="%(center_x).14f" y="%(center_y).14f" default_z="%(default_z)d"/>
 <TileFormat width="%(tilesize)d" height="%(tilesize)d" mime-type="%(mime)s" extension="%(tileformat)s" tile_row_type="%(tile_row_type)s"/>
 <TileSets profile="%(profile)s">
""" % args
  for z in range(int(self.mbtiles_minzoom), int(self.mbtiles_maxzoom)+1):
   s_xml += """  <TileSet href="%s%d" units-per-pixel="%.14f" order="%d"/>\n""" % (args['publishurl'], z, 156543.0339/2**z, z)
  s_xml += """ </TileSets>
</TileMap>
 """
  return s_xml

# from Landez project
# https://github.com/makinacorpus/landez
class EmptyCoverageError(Exception):
 """ Raised when coverage (tiles list) is empty """
 pass

# from Landez project
# https://github.com/makinacorpus/landez
class DownloadError(Exception):
 """ Raised when download at tiles URL fails DOWNLOAD_RETRIES times """
 pass

# from Landez project
# https://github.com/makinacorpus/landez
class ExtractionError(Exception):
 """ Raised when extraction of tiles from specified MBTiles has failed """
 pass

# from Landez project
# https://github.com/makinacorpus/landez
class InvalidFormatError(Exception):
 """ Raised when reading of MBTiles content has failed """
 pass

# from Landez project
# https://github.com/makinacorpus/landez
class TilesManager(object):
 def __init__(self, **kwargs):
  """
  Manipulates tiles in general. Gives ability to list required tiles on a
  bounding box, download them, render them, extract them from other mbtiles...
  Keyword arguments:
  cache -- use a local cache to share tiles between runs (default True)

  tiles_dir -- Local folder containing existing tiles if cache is
  True, or where temporary tiles will be written otherwise
    (default DEFAULT_TMP_DIR)
  tiles_url -- remote URL to download tiles (*default DEFAULT_TILES_URL*)
  tiles_headers -- HTTP headers to send (*default empty*)
  stylefile -- mapnik stylesheet file (*to render tiles locally*)

  mbtiles_file -- A MBTiles file providing tiles (*to extract its tiles*)

  wms_server -- A WMS server url (*to request tiles*)
  wms_layers -- The list of layers to be requested
  wms_options -- WMS parameters to be requested (see ``landez.reader.WMSReader``)
  tile_size -- default tile size (default DEFAULT_TILE_SIZE)
  tile_format -- default tile format (default DEFAULT_TILE_FORMAT)
  """
  self.tile_size = kwargs.get('tile_size', DEFAULT_TILE_SIZE)
  self.tile_format = kwargs.get('tile_format', DEFAULT_TILE_FORMAT)
  # Tiles Download
  self.tiles_url = kwargs.get('tiles_url', DEFAULT_TILES_URL)
  self.tiles_subdomains = kwargs.get('tiles_subdomains', DEFAULT_TILES_SUBDOMAINS)
  self.tiles_headers = kwargs.get('tiles_headers')
  # Tiles rendering
  self.stylefile = kwargs.get('stylefile')
  # Grids rendering
  self.grid_fields = kwargs.get('grid_fields', [])
  self.grid_layer = kwargs.get('grid_layer', 0)
  # MBTiles reading
  self.mbtiles_input = kwargs.get('mbtiles_input')
  # WMS requesting
  self.wms_server = kwargs.get('wms_server')
  self.wms_layers = kwargs.get('wms_layers', [])
  self.wms_options = kwargs.get('wms_options', {})
  if self.mbtiles_input:
   self.reader = MBTilesReader(self.mbtiles_input, self.tile_size)
  elif self.wms_server:
   assert self.wms_layers, _("Requires at least one layer (see ``wms_layers`` parameter)")
   self.reader = WMSReader(self.wms_server, self.wms_layers,self.tile_size, **self.wms_options)
   if 'format' in self.wms_options:
    self.tile_format = self.wms_options['format']
    logger.info(_("Tile format set to %s") % self.tile_format)
  elif self.stylefile:
   self.reader = MapnikRenderer(self.stylefile, self.tile_size)
  else:
   mimetype, encoding = mimetypes.guess_type(self.tiles_url)
   if mimetype and mimetype != self.tile_format:
    self.tile_format = mimetype
    logger.info(_("Tile format set to %s") % self.tile_format)
   self.reader = TileDownloader(self.tiles_url, headers=self.tiles_headers,subdomains=self.tiles_subdomains, tilesize=self.tile_size)
  # Tile files extensions
  self._tile_extension = mimetypes.guess_extension(self.tile_format, strict=False)
  assert self._tile_extension, _("Unknown format %s") % self.tile_format
  if self._tile_extension == '.jpe':
   self._tile_extension = '.jpeg'
  # Cache
  tiles_dir = kwargs.get('tiles_dir', DEFAULT_TMP_DIR)
  if kwargs.get('cache', True):
   self.cache = Disk(self.reader.basename, tiles_dir, extension=self._tile_extension)
  else:
   self.cache = Dummy(extension=self._tile_extension)
  # Overlays
  self._layers = []
  # Filters
  self._filters = []
  # Number of tiles rendered/downloaded here
  self.rendered = 0

 def tileslist(self, bbox, zoomlevels, tms_osm=False):
  """
  Build the tiles list within the bottom-left/top-right bounding
  box (minx, miny, maxx, maxy) at the specified zoom levels.
  Return a list of tuples (z,x,y)
  """
  mercator = GlobalMercator(tms_osm,self.tile_size,zoomlevels)
  return mercator.tileslist(bbox)

 def add_layer(self, tilemanager, opacity=1.0):
  """
  Add a layer to be blended (alpha-composite) on top of the tile.
  tilemanager -- a `TileManager` instance
  opacity -- transparency factor for compositing
  """
  assert has_pil, _("Cannot blend layers without python PIL")
  assert self.tile_size == tilemanager.tile_size, _("Cannot blend layers whose tile size differs")
  assert 0 <= opacity <= 1, _("Opacity should be between 0.0 (transparent) and 1.0 (opaque)")
  self.cache.basename += '%s%.1f' % (tilemanager.cache.basename, opacity)
  self._layers.append((tilemanager, opacity))

 def add_filter(self, filter_):
  """ Add an image filter for post-processing """
  assert has_pil, _("Cannot add filters without python PIL")
  self.cache.basename += filter_.basename
  self._filters.append(filter_)

 def get_metadata(self,i_parm=0):
  metadata_list = self.reader.metadata(i_parm)
  return metadata_list

 def tile(self, (z, x, y)):
  """
  Return the tile (binary) content of the tile and seed the cache.
  """
  output = self.cache.read((z, x, y))
  if output is None:
   print "TilesManager.tile calling sources.tile"
  output = self.reader.tile(z, x, y)
  if output is None:
   return None
  # Blend layers
  if len(self._layers) > 0:
   logger.debug(_("Will blend %s layer(s)") % len(self._layers))
   output = self._blend_layers(output, (z, x, y))
   # Apply filters
   for f in self._filters:
    image = f.process(self._tile_image(output))
    output = self._image_tile(image)
    # Save result to cache
    self.cache.save(output, (z, x, y))
    self.rendered += 1
  return output

 def grid(self, (z, x, y)):
  """ Return the UTFGrid content """
  # sources.py -> MapnikRenderer -> grid
  content = self.reader.grid(z, x, y, self.grid_fields, self.grid_layer)
  return content

 def _blend_layers(self, imagecontent, (z, x, y)):
  """
  Merge tiles of all layers into the specified tile path
  """
  result = self._tile_image(imagecontent)
  # Paste each layer
  for (layer, opacity) in self._layers:
   try:
    # Prepare tile of overlay, if available
    overlay = self._tile_image(layer.tile((z, x, y)))
   except (DownloadError, ExtractionError), e:
    logger.warn(e)
    continue
   # Extract alpha mask
   overlay = overlay.convert("RGBA")
   r, g, b, a = overlay.split()
   overlay = Image.merge("RGB", (r, g, b))
   a = ImageEnhance.Brightness(a).enhance(opacity)
   overlay.putalpha(a)
   mask = Image.merge("L", (a,))
   result.paste(overlay, (0, 0), mask)
   # Read result
  return self._image_tile(result)

 def _tile_image(self, data):
  """
  Tile binary content as PIL Image.
  """
  image = Image.open(StringIO(data))
  return image.convert('RGBA')

 def _image_tile(self, image):
  out = StringIO()
  image.save(out, self._tile_extension[1:])
  return out.getvalue()

# from Landez project
# https://github.com/makinacorpus/landez
class TileSource(object):
 def __init__(self, tilesize=None):
  if tilesize is None:
   tilesize = 256
  self.tilesize = tilesize
  self.basename = ''

  def tile(self, z, x, y):
   raise NotImplementedError

  def metadata(self):
   return dict()

# from Landez project
# https://github.com/makinacorpus/landez
class MBTilesReader(TileSource):
 def __init__(self, mbtiles_input, tilesize=None):
  super(MBTilesReader, self).__init__(tilesize)
  self.mbtiles_input = mbtiles_input.strip()
  self.basename = os.path.basename(self.mbtiles_input)
  self._con = None
  self._cur = None

 def _query(self, sql, *args):
  """ Executes the specified `sql` query and returns the cursor """
  if not self._con:
   logger.debug(_("MBTilesReader.Open MBTiles file '%s'") % self.mbtiles_input)
  self._con = sqlite3.connect(self.mbtiles_input)
  self._cur = self._con.cursor()
  sql = ' '.join(sql.split())
  logger.debug(_("Execute query '%s' %s") % (sql, args))
  try:
   self._cur.execute(sql, *args)
  except (sqlite3.OperationalError, sqlite3.DatabaseError), e:
   raise InvalidFormatError(_("%s while reading %s") % (e, self.filename))
  return self._cur

 def metadata(self,i_parm=0):
  rows = self._query('SELECT name, value FROM metadata ORDER BY name  COLLATE NOCASE ASC')
  rows = [(row[0], row[1]) for row in rows]
  if i_parm == 1:
   return rows
  return dict(rows)

 def zoomlevels(self):
  rows = self._query('SELECT DISTINCT(zoom_level) FROM tiles ORDER BY zoom_level')
  return [int(row[0]) for row in rows]

 def tile(self, z, x, y):
  logger.debug(_("MBTilesReader.Extract tile %s") % ((z, x, y),))
  y_mercator = (2**int(z) - 1) - int(y)
  rows = self._query('''SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?;''', (z, x, y_mercator))
  t = rows.fetchone()
  if not t:
   return None
   pass
   #   raise ExtractionError(_("Could not extract tile %s from %s") % ((z, x, y), self.filename))
  return t[0]

 def grid(self, z, x, y, callback=None):
  y_mercator = (2**int(z) - 1) - int(y)
  rows = self._query('''SELECT grid FROM grids WHERE zoom_level=? AND tile_column=? AND tile_row=?;''', (z, x, y_mercator))
  t = rows.fetchone()
  if not t:
   raise ExtractionError(_("Could not extract grid %s from %s") % ((z, x, y), self.filename))
  grid_json = json.loads(zlib.decompress(t[0]))
  rows = self._query('''SELECT key_name, key_json FROM grid_data  WHERE zoom_level=? AND tile_column=? AND tile_row=?;''', (z, x, y_mercator))
  # join up with the grid 'data' which is in pieces when stored in mbtiles file
  grid_json['data'] = {}
  grid_data = rows.fetchone()
  while grid_data:
   grid_json['data'][grid_data[0]] = json.loads(grid_data[1])
   grid_data = rows.fetchone()
   serialized = json.dumps(grid_json)
   if callback is not None:
    return '%s(%s);' % (callback, serialized)
  return serialized

 def find_coverage(self, zoom):
  """
  Returns the bounding box (minx, miny, maxx, maxy) of an adjacent
  group of tiles at this zoom level.
  """
  # Find a group of adjacent available tiles at this zoom level
  rows = self._query('''SELECT tile_column, tile_row FROM tiles  WHERE zoom_level=? ORDER BY tile_column, tile_row;''', (zoom,))
  t = rows.fetchone()
  xmin, ymin = t
  previous = t
  while t and t[0] - previous[0] <= 1:
   # adjacent, go on
   previous = t
   t = rows.fetchone()
   xmax, ymax = previous
   # Transform (xmin, ymin) (xmax, ymax) to pixels
   tile_size = self.tilesize
   bottomleft = (xmin * tile_size, (ymax + 1) * tile_size)
   topright = ((xmax + 1) * tile_size, ymin * tile_size)
   # Convert center to (lon, lat)
   mercator = GlobalMercator(False,tile_size,[z])
  return mercator.unproject_pixels(bottomleft, zoom) + mercator.unproject_pixels(topright, zoom)

# from Landez project
# https://github.com/makinacorpus/landez
class MBTilesBuilder(TilesManager):
 def __init__(self, **kwargs):
  """
  A MBTiles builder for a list of bounding boxes and zoom levels.
  mbtiles_output -- output MBTiles file (default DEFAULT_MBTILES_OUTPUT)
  tmp_dir -- temporary folder for gathering tiles (default DEFAULT_TMP_DIR/mbtiles_output)
  """
  super(MBTilesBuilder, self).__init__(**kwargs)
  self.mbtiles_output = kwargs.get('mbtiles_output', DEFAULT_MBTILES_OUTPUT)
  # Gather tiles for mbutil
  basename, ext = os.path.splitext(os.path.basename(self.mbtiles_output))
  self.tmp_dir = kwargs.get('tmp_dir', DEFAULT_TMP_DIR)
  self.tmp_dir = os.path.join(self.tmp_dir, basename)
  self.tile_format = kwargs.get('tile_format', DEFAULT_TILE_FORMAT)
  # Number of tiles in total
  self.nbtiles = 0
  self._bboxes = []
  self._metadata = []
  self.metadata_list=None
  self.s_y_type = 'tms'
  self.tms_osm=False
  self.mbtiles_format='jpg'
  self.mbtiles_verbose=True

 def add_coverage(self, bbox, zoomlevels):
  """
  Add a coverage to be included in the resulting mbtiles file.
  """
  self._bboxes.append((bbox, zoomlevels))

 def add_metadata(self, metdatadata_list):
  """
  Add metadata to be included in the resulting mbtiles file.
  """
  self._metadata.append((metdatadata_list, ))

 @property
 def zoomlevels(self):
  """
  Return the list of covered zoom levels
  """
  return self._bboxes[0][1]  #TODO: merge all coverages

 @property
 def bounds(self):
  """
  Return the bounding box of covered areas
  """
  return self._bboxes[0][0]  #TODO: merge all coverages

 def run(self, add=False):
  """
  Build a MBTile file.
  force -- overwrite if MBTiles file already exists.
  add -- TODO overwrite if MBTiles file already exists.
  """
  if os.path.exists(self.mbtiles_output):
   if add:
    logger.warn(_("%s already exists. Will be added to.") % self.mbtiles_output)
    # os.remove(self.mbtiles_output)
   else:
    # Already built, do not do anything.
    logger.info(_("%s already exists. Nothing to do.") % self.mbtiles_output)
    return
  extension = self.tile_format.split("image/")[-1]
  self.mbtiles_input_dir=os.path.dirname(self.mbtiles_input)+ '/'
  self.mbtiles_db_input=MbTiles()
  self.mbtiles_db_input.open_db(self.mbtiles_input,self.mbtiles_input_dir,self.mbtiles_format,self.s_y_type,self.mbtiles_verbose)
  self.metadata_input=self.mbtiles_db_input.fetch_metadata()
  self.tms_osm=self.mbtiles_db_input.tms_osm
  self.mbtiles_format=self.mbtiles_db_input.mbtiles_format
  self.s_y_type=self.mbtiles_db_input.s_y_type
  if len(self._bboxes) == 0:
   bbox = map(float, self.mbtiles_db_input.mbtiles_bounds.split(','))
   zoomlevels = range(int(self.mbtiles_db_input.mbtiles_minzoom), int(self.mbtiles_db_input.mbtiles_maxzoom)+1)
   self.add_coverage(bbox=bbox, zoomlevels=zoomlevels)
  # Compute list of tiles
  tileslist = set()
  for bbox, levels in self._bboxes:
   logger.debug(_("MBTilesBuilder.run: Compute list of tiles for bbox %s on zooms %s.") % (bbox, levels))
   bboxlist = self.tileslist(bbox, levels,self.tms_osm)
   logger.debug(_("Add %s tiles.") % len(bboxlist))
   tileslist = tileslist.union(bboxlist)
   logger.debug(_("MBTilesBuilder.run: %s tiles in total.") % len(tileslist))
  self.nbtiles = len(tileslist)
  if not self.nbtiles:
   raise EmptyCoverageError(_("No tiles are covered by bounding boxes : %s") % self._bboxes)
   logger.debug(_("%s tiles to be packaged.") % self.nbtiles)
  self.mbtiles_output=self.mbtiles_output.strip()
  self.mbtiles_output_dir=os.path.dirname(self.mbtiles_output)+ '/'
  self.mbtiles_db_output=MbTiles()
  self.mbtiles_db_output.open_db(self.mbtiles_output,self.mbtiles_output_dir,self.mbtiles_format,self.s_y_type,self.mbtiles_verbose)
  self.mbtiles_db_output.insert_metadata(self.metadata_input)
  # Go through whole list of tiles and read from input_db and store in output_db
  self.rendered = 0
  # something is 'unsorting' this
  for (z, x, y) in sorted(tileslist,key=operator.itemgetter(0,1,2)):
   image_data=self.mbtiles_db_input.retrieve_image(z,x,y)
   if not image_data is None:
    self.mbtiles_db_output.insert_image(z,x,y,image_data)
  self.mbtiles_db_input.close_db()
  # calculate the min/max zoom_levels and bounds
  self.mbtiles_db_output.retrieve_bounds()
  logger.debug(_("MBTilesBuilder.run: %s tiles were missing.") % self.rendered)
  # Package it!
  logger.info(_("Build MBTiles output file '%s'.") % self.mbtiles_output)
  for metadata_list in self._metadata:
   logger.debug(_("MBTilesBuilder.run: adding metadata %s .") % (metadata_list))
   self.mbtiles_db_output.insert_metadata(metadata_list[0])
  self.mbtiles_db_output.close_db()

 def run_orig(self, force=False):
  """
  Build a MBTile file.
  force -- overwrite if MBTiles file already exists.
  """
  if os.path.exists(self.mbtiles_output):
   if force:
    logger.warn(_("%s already exists. Overwrite.") % self.mbtiles_output)
    os.remove(self.mbtiles_output)
   else:
    # Already built, do not do anything.
    logger.info(_("%s already exists. Nothing to do.") % self.mbtiles_output)
    return
  # Clean previous runs
  self._clean_gather()
  # If no coverage added, use bottom layer metadata
  if len(self._layers) > 0:
   bottomlayer = self._layers[0]
   metadata = bottomlayer.reader.metadata()
   if len(self._bboxes) == 0:
    if 'bounds' in self.metadata:
     logger.debug(_("Use bounds of bottom layer %s") % bottomlayer)
     bbox = map(float, metadata.get('bounds', '').split(','))
     zoomlevels = range(int(metadata.get('minzoom', 0)), int(metadata.get('maxzoom', 0)))
     self.add_coverage(bbox=bbox, zoomlevels=zoomlevels)
  # Compute list of tiles
  tileslist = set()
  for bbox, levels in self._bboxes:
   logger.debug(_("MBTilesBuilder.run: Compute list of tiles for bbox %s on zooms %s.") % (bbox, levels))
   bboxlist = self.tileslist(bbox, levels,self.tms_osm)
   logger.debug(_("Add %s tiles.") % len(bboxlist))
   tileslist = tileslist.union(bboxlist)
   logger.debug(_("MBTilesBuilder.run: %s tiles in total.") % len(tileslist))
  self.nbtiles = len(tileslist)
  if not self.nbtiles:
   raise EmptyCoverageError(_("No tiles are covered by bounding boxes : %s") % self._bboxes)
   logger.debug(_("%s tiles to be packaged.") % self.nbtiles)
  # Go through whole list of tiles and gather them in tmp_dir
  self.rendered = 0
  for (z, x, y) in sorted(tileslist,key=operator.itemgetter(0,1,2)):
   self._gather((z, x, y))
  logger.debug(_("MBTilesBuilder.run: %s tiles were missing.") % self.rendered)
  self.metadata_list = self.get_metadata(1)
  # Some metadata
  middlezoom = self.zoomlevels[len(self.zoomlevels)/2]
  lat = self.bounds[1] + (self.bounds[3] - self.bounds[1])/2
  lon = self.bounds[0] + (self.bounds[2] - self.bounds[0])/2
  metadata = {}
  metadata['format'] = self._tile_extension[1:]
  metadata['minzoom'] = self.zoomlevels[0]
  metadata['maxzoom'] = self.zoomlevels[-1]
  metadata['bounds'] = '%s,%s,%s,%s' % tuple(self.bounds)
  metadata['center'] = '%s,%s,%s' % (lon, lat, middlezoom)
  #display informations from the grids on hover
  content_to_display = ''
  for field_name in self.grid_fields:
   content_to_display += "{{{ %s }}}<br>" % field_name
  metadata['template'] = '{{#__location__}}{{/__location__}} {{#__teaser__}} \
       %s {{/__teaser__}}{{#__full__}}{{/__full__}}' % content_to_display
  metadatafile = os.path.join(self.tmp_dir, 'metadata.json')
  with open(metadatafile, 'w') as output:
   json.dump(metadata, output)
  # TODO: add UTF-Grid of last layer, if any
  # Package it!
  logger.info(_("Build MBTiles file '%s'.") % self.mbtiles_output)
  extension = self.tile_format.split("image/")[-1]
  self.mbtiles_output=self.mbtiles_output.strip()
  self.mbtiles_output_dir=os.path.dirname(self.mbtiles_output)+ '/'
  self.mbtiles_format=extension
  self.mbtiles_db_output=MbTiles()
  self.mbtiles_db_output.open_db(self.mbtiles_output,self.mbtiles_output_dir,self.mbtiles_format,self.s_y_type,self.mbtiles_verbose)
  self.mbtiles_db_output.insert_metadata(self.metadata_list)
  self.mbtiles_db_output.mbtiles_from_disk(self.tmp_dir)
  for metadata_list in self._metadata:
   logger.debug(_("MBTilesBuilder.run: adding metadata %s .") % (metadata_list))
   self.mbtiles_db_output.insert_metadata(metadata_list[0])
  self.mbtiles_db_output.close_db()
  try:
   os.remove("%s-journal" % self.mbtiles_output)  # created by mbutil
  except OSError, e:
   pass
  self._clean_gather()

 def _gather(self, (z, x, y)):
  files_dir, tile_name = self.cache.tile_file((z, x, y))
  tmp_dir = os.path.join(self.tmp_dir, files_dir)
  if not os.path.isdir(tmp_dir):
   os.makedirs(tmp_dir)
  print "MBTilesBuilder._gather calling tile"
  tilecontent = self.tile((z, x, y))
  if tilecontent:
   tilepath = os.path.join(tmp_dir, tile_name)
   with open(tilepath, 'wb') as f:
    f.write(tilecontent)
   if len(self.grid_fields) > 0:
    gridcontent = self.grid((z, x, y))
    gridpath = "%s.%s" % (os.path.splitext(tilepath)[0], 'grid.json')
    with open(gridpath, 'w') as f:
     f.write(gridcontent)

 def _clean_gather(self):
  logger.debug(_("Clean-up %s") % self.tmp_dir)
  try:
   shutil.rmtree(self.tmp_dir)
   #Delete parent folder only if empty
   try:
    parent = os.path.dirname(self.tmp_dir)
    os.rmdir(parent)
    logger.debug(_("Clean-up parent %s") % parent)
   except OSError:
    pass
  except OSError:
   pass

# from Landez project
# https://github.com/makinacorpus/landez
class ImageExporter(TilesManager):
 def __init__(self, **kwargs):
  """
  Arrange the tiles and join them together to build a single big image.
  """
  super(ImageExporter, self).__init__(**kwargs)

 def grid_tiles(self, bbox, zoomlevel):
  """
  Return a grid of (x, y) tuples representing the juxtaposition
  of tiles on the specified ``bbox`` at the specified ``zoomlevel``.
  """
  tiles = self.tileslist(bbox, [zoomlevel])
  grid = {}
  for (z, x, y) in sorted(tiles,key=operator.itemgetter(0,1,2)):
   if not grid.get(y):
    grid[y] = []
    grid[y].append(x)
    sortedgrid = []
    for y in sorted(grid.keys()):
     sortedgrid.append([(x, y) for x in sorted(grid[y])])
  return sortedgrid

 def export_image(self, bbox, zoomlevel, imagepath):
  """
  Writes to ``imagepath`` the tiles for the specified bounding box and zoomlevel.
  """
  assert has_pil, _("Cannot export image without python PIL")
  grid = self.grid_tiles(bbox, zoomlevel)
  width = len(grid[0])
  height = len(grid)
  widthpix = width * self.tile_size
  heightpix = height * self.tile_size
  result = Image.new("RGBA", (widthpix, heightpix))
  offset = (0, 0)
  for i, row in enumerate(grid):
   for j, (x, y) in enumerate(row):
     offset = (j * self.tile_size, i * self.tile_size)
     img = self._tile_image(self.tile((zoomlevel, x, y)))
     result.paste(img, offset)
  logger.info(_("Save resulting image to '%s'") % imagepath)
  result.save(imagepath)

# from Landez project
# https://github.com/makinacorpus/landez
class TileDownloader(TileSource):
 def __init__(self, url, headers=None, subdomains=None, tilesize=None):
  super(TileDownloader, self).__init__(tilesize)
  self.tiles_url = url
  self.tiles_subdomains = subdomains or ['a', 'b', 'c']
  parsed = urlparse(self.tiles_url)
  self.basename = parsed.netloc
  self.headers = headers or {}

 def tile(self, z, x, y):
  """
  Download the specified tile from `tiles_url`
  """
  logger.debug(_("Download tile %s") % ((z, x, y),))
  # Render each keyword in URL ({s}, {x}, {y}, {z}, {size} ... )
  size = self.tilesize
  s = self.tiles_subdomains[(x + y) % len(self.tiles_subdomains)];
  try:
   url = self.tiles_url.format(**locals())
  except KeyError, e:
   raise DownloadError(_("Unknown keyword %s in URL") % e)
  logger.debug(_("Retrieve tile at %s") % url)
  r = DOWNLOAD_RETRIES
  sleeptime = 1
  while r > 0:
   try:
    request = urllib2.Request(url)
    for header, value in self.headers.items():
     request.add_header(header, value)
     stream = urllib2.urlopen(request)
     assert stream.getcode() == 200
     return stream.read()
   except (AssertionError, IOError), e:
    logger.debug(_("Download error, retry (%s left). (%s)") % (r, e))
    r -= 1
    time.sleep(sleeptime)
    # progressivly sleep longer to wait for this tile
    if (sleeptime <= 10) and (r % 2 == 0):
     sleeptime += 1  # increase wait
  raise DownloadError(_("Cannot download URL %s") % url)

# from Landez project
# https://github.com/makinacorpus/landez
class WMSReader(TileSource):
 def __init__(self, url, layers, tilesize=None, **kwargs):
  super(WMSReader, self).__init__(tilesize)
  self.basename = '-'.join(layers)
  self.url = url
  self.wmsParams = dict(
   service='WMS',
   request='GetMap',
   version='1.1.1',
   styles='',
   format=DEFAULT_TILE_FORMAT,
   transparent=False,
   layers=','.join(layers),
   width=self.tilesize,
   height=self.tilesize,
  )
  self.wmsParams.update(**kwargs)
  projectionKey = 'srs'
  if parse_version(self.wmsParams['version']) >= parse_version('1.3'):
   projectionKey = 'crs'
  self.wmsParams[projectionKey] = GlobalMercator.NAME

 def tile(self, z, x, y):
  logger.debug(_("Request WMS tile %s") % ((z, x, y),))
  mercator = GlobalMercator(False,tile_size,[z])
  bbox = mercator.tile_bbox((z, x, y))
  bbox = mercator.project(bbox[:2]) + mercator.project(bbox[2:])
  bbox = ','.join(map(str, bbox))
  # Build WMS request URL
  encodedparams = urllib.urlencode(self.wmsParams)
  url = "%s?%s" % (self.url, encodedparams)
  url += "&bbox=%s" % bbox   # commas are not encoded
  try:
   logger.debug(_("Download '%s'") % url)
   f = urllib2.urlopen(url)
   header = f.info().typeheader
   assert header == self.wmsParams['format'], "Invalid WMS response type : %s" % header
   return f.read()
  except (AssertionError, IOError):
   raise ExtractionError

# from Landez project
# https://github.com/makinacorpus/landez
class MapnikRenderer(TileSource):
 def __init__(self, stylefile, tilesize=None):
  super(MapnikRenderer, self).__init__(tilesize)
  assert has_mapnik, _("Cannot render tiles without mapnik !")
  self.stylefile = stylefile
  self.basename = os.path.basename(self.stylefile)
  self._mapnik = None
  self._prj = None

 def tile(self, z, x, y):
  """
  Render the specified tile with Mapnik
  """
  logger.debug(_("Render tile %s") % ((z, x, y),))
  mercator = GlobalMercator(False,tilesize,[z])
  return self.render(mercator.tile_bbox((z, x, y)))

 def _prepare_rendering(self, bbox, width=None, height=None):
  if not self._mapnik:
   self._mapnik = mapnik.Map(width, height)
  # Load style XML
  mapnik.load_map(self._mapnik, self.stylefile, True)
  # Obtain <Map> projection
  self._prj = mapnik.Projection(self._mapnik.srs)
  # Convert to map projection
  assert len(bbox) == 4, _("Provide a bounding box tuple (minx, miny, maxx, maxy)")
  c0 = self._prj.forward(mapnik.Coord(bbox[0], bbox[1]))
  c1 = self._prj.forward(mapnik.Coord(bbox[2], bbox[3]))
  # Bounding box for the tile
  bbox = mapnik.Box2d(c0.x, c0.y, c1.x, c1.y)
  self._mapnik.resize(width, height)
  self._mapnik.zoom_to_box(bbox)
  self._mapnik.buffer_size = 128

 def render(self, bbox, width=None, height=None):
  """
  Render the specified tile with Mapnik
  """
  width = width or self.tilesize
  height = height or self.tilesize
  self._prepare_rendering(bbox, width=width, height=height)
  # Render image with default Agg renderer
  tmpfile = NamedTemporaryFile(delete=False)
  im = mapnik.Image(width, height)
  mapnik.render(self._mapnik, im)
  im.save(tmpfile.name, 'png256')  # TODO: mapnik output only to file?
  tmpfile.close()
  content = open(tmpfile.name).read()
  os.unlink(tmpfile.name)
  return content

 def grid(self, z, x, y, fields, layer):
  """
  Render the specified grid with Mapnik
  """
  logger.debug(_("Render grid %s") % ((z, x, y),))
  mercator = GlobalMercator(False,self.tilesize,[z])
  return self.render_grid(mercator.tile_bbox((z, x, y)), fields, layer)

 def render_grid(self, bbox, grid_fields, layer, width=None, height=None):
  """
  Render the specified grid with Mapnik
  """
  width = width or self.tilesize
  height = height or self.tilesize
  self._prepare_rendering(bbox, width=width, height=height)
  grid = mapnik.Grid(width, height)
  mapnik.render_layer(self._mapnik, grid, layer=layer, fields=grid_fields)
  grid = grid.encode()
  return json.dumps(grid)

# from Landez project
# https://github.com/makinacorpus/landez
class Cache(object):
 def __init__(self, **kwargs):
  self.extension = kwargs.get('extension', '.png')

 def tile_file(self, (z, x, y)):
  tile_dir = os.path.join("%s" % z, "%s" % x)
  y_mercator = (2**z - 1) - y
  tile_name = "%s%s" % (y_mercator, self.extension)
  return tile_dir, tile_name

 def read(self, (z, x, y)):
  raise NotImplementedError

 def save(self, body, (z, x, y)):
  raise NotImplementedError

 def remove(self, (z, x, y)):
  raise NotImplementedError

 def clean(self):
  raise NotImplementedError

# from Landez project
# https://github.com/makinacorpus/landez
class Dummy(Cache):
 def read(self, (z, x, y)):
  return None

 def save(self, body, (z, x, y)):
  pass

 def remove(self, (z, x, y)):
  pass

 def clean(self):
  pass

# from Landez project
# https://github.com/makinacorpus/landez
class Disk(Cache):
 def __init__(self, basename, folder, **kwargs):
  super(Disk, self).__init__(**kwargs)
  self._basename = None
  self._basefolder = folder
  self.folder = folder
  self.basename = basename

 @property
 def basename(self):
  return self._basename

 @basename.setter
 def basename(self, basename):
  self._basename = basename
  subfolder = re.sub(r'[^a-z^A-Z^0-9]+', '', basename.lower())
  self.folder = os.path.join(self._basefolder, subfolder)

 def tile_fullpath(self, (z, x, y)):
  tile_dir, tile_name = self.tile_file((z, x, y))
  tile_abs_dir = os.path.join(self.folder, tile_dir)
  return os.path.join(tile_abs_dir, tile_name)

 def remove(self, (z, x, y)):
  tile_abs_uri = self.tile_fullpath((z, x, y))
  os.remove(tile_abs_uri)
  parent = os.path.dirname(tile_abs_uri)
  i = 0
  while i <= 3:  # try to remove 3 levels (cache/z/x/)
   try:
    os.rmdir(parent)
    parent = os.path.dirname(parent)
    i += 1
   except OSError:
    break

 def read(self, (z, x, y)):
  tile_abs_uri = self.tile_fullpath((z, x, y))
  if os.path.exists(tile_abs_uri):
   logger.debug(_("Found %s") % tile_abs_uri)
   return open(tile_abs_uri, 'rb').read()
  return None

 def save(self, body, (z, x, y)):
  tile_abs_uri = self.tile_fullpath((z, x, y))
  tile_abs_dir = os.path.dirname(tile_abs_uri)
  if not os.path.isdir(tile_abs_dir):
   os.makedirs(tile_abs_dir)
  logger.debug(_("Save %s bytes to %s") % (len(body), tile_abs_uri))
  open(tile_abs_uri, 'wb').write(body)

 def clean(self):
  logger.debug(_("Clean-up %s") % self.folder)
  try:
   shutil.rmtree(self.folder)
  except OSError:
   logger.warn(_("%s was missing or read-only.") % self.folder)
