#!/usr/bin/env python
# - coding: utf-8 -*-
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

from osgeo import gdal,osr

import collections
import json
import logging
import mimetypes
import math
import operator
import os
from pkg_resources import parse_version
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib
import urllib2
from urlparse import urlparse
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
DEFAULT_TILES_URL = "http://{s}.tile.openstreetmap.org/{z}/{x}/{y_osm}.png"
""" Default tiles subdomains """
DEFAULT_TILES_SUBDOMAINS = list("abc")
""" Base temporary folder """
DEFAULT_TMP_DIR = os.path.join(tempfile.gettempdir(), 'mapmbtiles')
""" Default output MBTiles file """
DEFAULT_MBTILES_OUTPUT = os.path.join(os.getcwd(), "mbtiles_output.mbtiles")
""" Default tile size in pixels (*useless* in remote rendering) """
DEFAULT_TILE_SIZE = 256
""" Default tile format (mime-type) """
DEFAULT_TILE_FORMAT = 'image/jpeg'
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
  self.jpg_quality=75
  self.pil_format='JPEG'
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
  if mbtiles_format.find("image/") == -1:
   mbtiles_format.replace("image/ ","")
  if mbtiles_format == "jpeg":
   mbtiles_format="jpg"
  if mbtiles_format == "png":
   self.mbtiles_format=mbtiles_format
   self.pil_format='PNG'
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
    logger.info(_("MbTiles : [open_db] : creating: [%s]") % self.s_path_db)
   self.mbtiles_create()
  else:
   if self.verbose:
    logger.info(_("MbTiles : [open_db] : opening: [%s]") % self.s_path_db)
   self.fetch_metadata()

 def close_db(self):
  if self.verbose:
   logger.info(_("MbTiles : [close_db] : closing: [%s]") % self.s_path_db)
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
   logger.error(_("MbTiles : Could not connect to database: Error %s:") % e.args[0])
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
   logger.info(_("MbTiles : optimize_database: analyzing db [%s]") % "ANALYZE;")
  self.mbtiles_cursor.execute("""ANALYZE;""")
  if self.verbose:
   logger.info(_("MbTiles : optimize_database: cleaning db [%s]") % "VACUUM;")
  self.mbtiles_cursor.execute("""VACUUM;""")
  if self.verbose:
   logger.info(_("MbTiles : optimize_database: [%s]") % self.s_path_db)

 def insert_metadata(self,metadata_list):
  if metadata_list:
   if self.verbose:
    # logger.info(_("MbTiles : insert_metadata:: [%s]") % metadata_list)
    pass
   try:
    # ERROR:mapmbtiles.mbtiles:MbTiles : insert_metadata: Error You must not use 8-bit bytestrings unless you use a text_factory that can interpret 8-bit bytestrings (like text_factory = str). It is highly recommended that you instead just switch your application to Unicode strings.:
    # repr(metadata_list)
    self.mbtiles_cursor.executemany("INSERT OR REPLACE INTO metadata VALUES(?,?)",metadata_list)
    self.sqlite3_connection.commit()
   except sqlite3.Error, e:
    self.sqlite3_connection.rollback()
    logger.error(_("MbTiles : insert_metadata: Error %s:") % e.args[0])
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
  s_tile_id="{0}-{1}-{2}.{3}".format(str(tz),str(tx),str(ty),self.s_y_type)
  s_tile_id,output_image=self.check_image(s_tile_id,image_data)
  if output_image:
   image_data=output_image
  sql_insert_map="INSERT OR REPLACE INTO map (tile_id,zoom_level,tile_column,tile_row,grid_id) VALUES(?,?,?,?,?);";
  map_values = [(s_tile_id,tz,tx,ty,'')]
  sql_insert_image="INSERT OR REPLACE INTO images (tile_id,tile_data) VALUES(?,?);"
  image_values = [(s_tile_id,buffer(image_data))]
  # sqlite3.Binary(image_data)
  if self.verbose:
   logger.info(_("MbTiles : insert_image: %d,%d,%d id[%s]") % (tz,tx,ty,s_tile_id))
  try:
   self.mbtiles_cursor.executemany(sql_insert_map,map_values)
   self.mbtiles_cursor.executemany(sql_insert_image,image_values)
   self.sqlite3_connection.commit()
  except sqlite3.Error, e:
   self.sqlite3_connection.rollback()
   logger.error(_("MbTiles : insert_image: Error %s:") % e.args[0])

 def check_image(self,s_tile_id,image_data):
  # a list of (count, color) tuples or None, max amount [we only want information about a blank image]
  output_data=None
  input_image = Image.open(BytesIO(image_data))
  colors = input_image.getcolors(1)
  if self.pil_format != input_image.format:
   if self.pil_format == "JPEG":
    if input_image.mode != "RGB":
     input_image=input_image.convert('RGB')
    # http://effbot.org/imagingbook/pil-index.htm#appendixes
    input_image.save(s_tile_id, format="JPEG", quality=self.jpg_quality, optimize=True, progressive=False)
   else:
    input_image.save(s_tile_id, format="PNG",optimize=True)
   f = open(s_tile_id,'rb')
   output_data = f.read()
   f.close()
   os.remove(s_tile_id)
   input_image = Image.open(BytesIO(output_data))
   colors = input_image.getcolors(1)
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
   # MbTiles : check_image: [(65536, (255, 255, 255))] 18-140785-176149.tms
   # colors = len(filter(None,image_img.histogram()))
  return s_tile_id,output_data

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
   # logger.info(_("MbTiles : retrieve_bounds: i_zoom %d min(%d,%d) ; max(%d,%d)")% (i_zoom,i_x_min,i_y_min,i_x_max,i_y_max))
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
     logger.info(_("MbTiles : retrieve_zoom_images: source[%s] : fetching[%s]") % s_tile_source,s_tile_id)
    if image_data is None:
     # 1 / 8051 /media/gb_1500/maps/geo_tiff/rd_Berlin_Schmettau/18-140798-176204.jpg
     # [19-281597-352408.jpg] istilie_id '0-0-0.rgb'
     s_tile_id_orig=s_tile_id
     s_tile_id=self.count_tiles(tz,x,y,10)
     if self.verbose:
      logger.info(_("MbTiles : retrieve_zoom_images: fetching[%s] failed ; may be a rgb-image ; attempting [%s]") % s_tile_id_orig,s_tile_id)
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
   logger.error(_("MbTiles : mbtiles_from_disk: directory does not exist : [%s] ") % directory_path)
   return
  if self.verbose:
   logger.info(_("MbTiles : mbtiles_from_disk: fetching[%s] ") % directory_path)
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
   logger.info(_("MbTiles : mbtiles_from_disk: [%s] - Habe fertig") % self.s_path_db)

 def mbtiles_to_disk(self,directory_path):
  if self.verbose:
   logger.info(_("MbTiles : mbtiles_to_disk: reading [%s]]") % self.s_path_db)
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
   logger.info(_("MbTiles : mbtiles_to_disk: created directory[%s] with %d tiles - Habe fertig") % directory_path,count)

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
 # from Landez project
 # https://github.com/makinacorpus/landez
 def zoomlevels(self):
  rows = self.mbtiles_cursor.execute('SELECT DISTINCT(zoom_level) FROM tiles ORDER BY zoom_level')
  return [int(row[0]) for row in rows]

 # -------------------------------------------------------------------------
 # from Landez project
 # https://github.com/makinacorpus/landez
 def metadata(self,i_parm=0):
  rows = self.mbtiles_cursor.execute('SELECT name, value FROM metadata ORDER BY name  COLLATE NOCASE ASC')
  rows = [(row[0], row[1]) for row in rows]
  if i_parm == 1:
   return rows
  return dict(rows)

 # -------------------------------------------------------------------------
 # from Landez project
 # https://github.com/makinacorpus/landez
 def find_coverage(self, zoom):
  """
  Returns the bounding box (minx, miny, maxx, maxy) of an adjacent
  group of tiles at this zoom level.
  """
  # Find a group of adjacent available tiles at this zoom level
  rows = self.mbtiles_cursor.execute('''SELECT tile_column, tile_row FROM tiles  WHERE zoom_level=? ORDER BY tile_column, tile_row;''', (zoom,))
  tile = rows.fetchone()
  xmin, ymin = tile
  tile_prev = tile
  while tile and tile[0] - tile_prev[0] <= 1:
   # adjacent, go on
   tile_prev = tile
   tile = rows.fetchone()
   xmax, ymax = tile_prev
   # Transform (xmin, ymin) (xmax, ymax) to pixels
   tile_size = self.tilesize
   bottomleft = (xmin * tile_size, (ymax + 1) * tile_size)
   topright = ((xmax + 1) * tile_size, ymin * tile_size)
   # Convert center to (lon, lat)
   mercator = GlobalMercator(self.tms_osm,tile_size,[zoom])
  return mercator.unproject_pixels(bottomleft, zoom) + mercator.unproject_pixels(topright, zoom)

 # -------------------------------------------------------------------------
 # from Landez project
 # https://github.com/makinacorpus/landez
 def grid(self, z, x, y, callback=None):
  y_mercator = (2**int(z) - 1) - int(y)
  rows = self.mbtiles_cursor.execute('''SELECT grid FROM grids WHERE zoom_level=? AND tile_column=? AND tile_row=?;''', (z, x, y_mercator))
  grid = rows.fetchone()
  if not grid:
   raise ExtractionError(_("Could not extract grid %s from %s") % ((z, x, y),self.s_path_db))
  grid_json = json.loads(zlib.decompress(grid[0]))
  rows = self.mbtiles_cursor.execute('''SELECT key_name, key_json FROM grid_data  WHERE zoom_level=? AND tile_column=? AND tile_row=?;''', (z, x, y_mercator))
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

 # -------------------------------------------------------------------------
 # from gdal2tiles project
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
class TileSource(object):
 def __init__(self, tilesize=None):
  if tilesize is None:
   tilesize = 256
  self.tilesize = tilesize
  self.basename = ''
  self.metadata_input=None
  self.tms_osm=False
  self.s_y_type = 'tms'
  self.mbtiles_format='jpg'
  self.mbtiles_verbose=False
  self.mbtiles_bounds="-180.00000,-85.05113,180.00000,85.05113"
  self.mbtiles_minzoom="0"
  self.mbtiles_maxzoom="22"

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
  self.mbtiles_input_dir=os.path.dirname(self.mbtiles_input)+ '/'
  self.mbtiles_db_input=MbTiles()
  self.mbtiles_db_input.open_db(self.mbtiles_input,self.mbtiles_input_dir,self.mbtiles_format,self.s_y_type,self.mbtiles_verbose)
  self.metadata_input=self.mbtiles_db_input.fetch_metadata()
  self.tms_osm=self.mbtiles_db_input.tms_osm
  self.mbtiles_format=self.mbtiles_db_input.mbtiles_format
  self.s_y_type=self.mbtiles_db_input.s_y_type
  self.mbtiles_bounds=self.mbtiles_db_input.mbtiles_bounds
  self.mbtiles_minzoom=self.mbtiles_db_input.mbtiles_minzoom
  self.mbtiles_maxzoom=self.mbtiles_db_input.mbtiles_maxzoom

 def metadata(self,i_parm=0):
  return self.mbtiles_db_input.metadata(i_parm)

 def zoomlevels(self):
  return self.mbtiles_db_input.zoomlevels()

 def tile(self, z, x, y):
  logger.debug(_("MBTilesReader.Extract tile %s") % ((z, x, y),))
  # y_mercator = (2**int(z) - 1) - int(y)
  return self.mbtiles_db_input.retrieve_image(z,x,y)

 def grid(self, z, x, y, callback=None):
  return self.mbtiles_db_input.grid(z,x,y, callback)

 def find_coverage(self, zoom):
  """
  Returns the bounding box (minx, miny, maxx, maxy) of an adjacent
  group of tiles at this zoom level.
  """
  # Find a group of adjacent available tiles at this zoom level
  return self.mbtiles_db_input.find_coverage(zoom)

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
   self.reader.mbtiles_format=self.tile_format
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
   # logger.info(_("TilesManager.tile calling sources.tile: ") )
   pass
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
  image = Image.open(BytesIO(data))
  return image.convert('RGBA')

 def _image_tile(self, image):
  out_image = BytesIO()
  image.save(out_image, self._tile_extension[1:])
  return out_image.getvalue()

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

 def run(self, add=False, i_parm=0):
  """
  Build a MBTile file.
  add -- add if MBTiles file already exists.
  i_parm -- 1 : show info only
  """
  if os.path.exists(self.mbtiles_output):
   if add:
    logger.warn(_("%s already exists. Will be added to.") % self.mbtiles_output)
    # os.remove(self.mbtiles_output)
   else:
    # Already built, do not do anything.
    logger.info(_("%s already exists. Nothing to do.") % self.mbtiles_output)
    return
  if len(self._bboxes) == 0:
   bbox = map(float, self.reader.mbtiles_bounds.split(','))
   zoomlevels = range(int(self.reader.mbtiles_minzoom), int(self.reader.mbtiles_maxzoom)+1)
   self.add_coverage(bbox=bbox, zoomlevels=zoomlevels)
  # Compute list of tiles
  tileslist = set()
  for bbox, levels in self._bboxes:
   logger.debug(_("MBTilesBuilder.run: Compute list of tiles for bbox %s on zooms %s.") % (bbox, levels))
   bboxlist,tile_bounds = self.tileslist(bbox, levels,self.reader.tms_osm)
   logger.debug(_("Add %s tiles.") % len(bboxlist))
   tileslist = tileslist.union(bboxlist)
   logger.debug(_("MBTilesBuilder.run: %s tiles in total.") % len(tileslist))
  self.nbtiles = len(tileslist)
  if not self.nbtiles:
   raise EmptyCoverageError(_("No tiles are covered by bounding boxes : %s") % self._bboxes)
  if i_parm == 1:
   logger.info(_("-I-> Computed list of [%d] tiles for bbox %s on zooms %s.") % (self.nbtiles,bbox, levels))
   logger.info(_("-I-> MBTilesBuilder.run: i_parm[%d] ; set i_parm=0 to run ; will now exit.") % i_parm)
   return
  self.mbtiles_output=self.mbtiles_output.strip()
  self.mbtiles_output_dir=os.path.dirname(self.mbtiles_output)+ '/'
  self.mbtiles_db_output=MbTiles()
  self.mbtiles_db_output.open_db(self.mbtiles_output,self.mbtiles_output_dir,self.reader.mbtiles_format,self.reader.s_y_type,self.reader.mbtiles_verbose)
  if self.reader.metadata_input:
   self.mbtiles_db_output.insert_metadata(self.reader.metadata_input)
  # Go through whole list of tiles and read from input_db and store in output_db
  self.rendered = 0
  # something is 'unsorting' this
  for (z, x, y) in sorted(tileslist,key=operator.itemgetter(0,1,2)):
   image_data=self.tile((z,x,y))
   if not image_data is None:
    self.mbtiles_db_output.insert_image(z,x,y,image_data)
  # calculate the min/max zoom_levels and bounds
  self.mbtiles_db_output.retrieve_bounds()
  logger.debug(_("MBTilesBuilder.run: %s tiles were missing.") % self.rendered)
  # Package it!
  logger.info(_("Build MBTiles output file '%s'.") % self.mbtiles_output)
  for metadata_list in self._metadata:
   logger.debug(_("MBTilesBuilder.run: adding metadata %s .") % (metadata_list))
   self.mbtiles_db_output.insert_metadata(metadata_list[0])
  self.mbtiles_db_output.close_db()

# from Landez project
# https://github.com/makinacorpus/landez
# http://effbot.org/imagingbook/pil-index.htm#appendixes
class ImageExporter(TilesManager):
 def __init__(self, **kwargs):
  """
  Arrange the tiles and join them together to build a single big image.
  Sample Image: 1861_Mercator_Europe zoom_level 8
  - given       bbox: -8.0,36.0,80.0,77.0
  - calulated bbox: -8.4375, 35.46066995149529, 80.15625, 77.157162522661
  Image Size is 16128, 15872 ; Pixel Size = (0.005493164062500,-0.002627047163002)
  Origin = (-8.437500000000000,77.157162522660997)
  PNG:    370   MB
  TIF : 1.000   MB [NONE]
  TIF : 1.000   MB [PACKBITS]  - took 1 minute to create
  TIF :   404.7 MB [DEFLATE,PREDICTOR=2,ZLEVEL=8] - took 13 minutes to create
  TIF :   404.7 MB [DEFLATE,PREDICTOR=2,ZLEVEL=9] - took 13 minutes to create
  TIF :   472.5 MB [LZW,PREDICTOR=2] - took 1 minute to create [default if nothing is supplid]
  TIF :   735.8 MB [LZW,PREDICTOR=1] - took 1 minute to create
  """
  super(ImageExporter, self).__init__(**kwargs)
  # COMPRESS=PACKBITS
  # PIL: TIFF uncompressed, or Packbits, LZW, or JPEG compressed images. In the current version, PIL always writes uncompressed TIFF files
  # http://linfiniti.com/2011/05/gdal-efficiency-of-various-compression-algorithms/
  # predictor for 'DEFLATE' or 'LZW' : 1 or 2
  i_tiff_compression_predictor=2
  # zlevel for 'DEFLATE'  : 1 to 9
  i_tiff_compression_zlevel=8
  self.jpg_quality=75
  self.tiff_compression=[]
  self._metadata = []
  if self.reader.metadata_input:
   self.metadata_input=self.reader.metadata_input
  self.tiff_compress = kwargs.get('tiff_compression', "LZW")
  self.tiff_compress =self.tiff_compress.upper()
  self.jpg_quality = kwargs.get('jpg_quality', self.jpg_quality)
  if self.jpg_quality < 1 or self.jpg_quality > 95:
   self.jpg_quality=75
  i_tiff_compression_predictor = kwargs.get('tiff_predictor', i_tiff_compression_predictor)
  if i_tiff_compression_predictor < 1 or i_tiff_compression_predictor > 2:
   i_tiff_compression_predictor=2
  i_tiff_compression_zlevel = kwargs.get('tiff_zlevel', i_tiff_compression_zlevel)
  if i_tiff_compression_zlevel < 1 or i_tiff_compression_zlevel > 9:
   i_tiff_compression_predictor=8
  if self.tiff_compress == "PACKBITS" :
   self.tiff_compression.append('COMPRESS=PACKBITS')
  elif self.tiff_compress == "DEFLATE":
   self.tiff_compression.append('COMPRESS=%s' % 'DEFLATE')
   self.tiff_compression.append('PREDICTOR=%d' % i_tiff_compression_predictor)
   self.tiff_compression.append('ZLEVEL=%d' % i_tiff_compression_zlevel)
  elif self.tiff_compress == "LZW":
   self.tiff_compression.append('COMPRESS=%s' % 'LZW')
   self.tiff_compression.append('PREDICTOR=%d' % i_tiff_compression_predictor)
  elif self.tiff_compress == "NONE":
   self.tiff_compression.append('COMPRESS=NONE')

 def add_metadata(self, metdatadata_list):
  """
  Add metadata to be included in the resulting mbtiles file.
  """
  self._metadata.append((metdatadata_list, ))

 def grid_tiles(self, bbox, zoomlevel):
  """
  Return a grid of (x, y) tuples representing the juxtaposition
  of tiles on the specified ``bbox`` at the specified ``zoomlevel``.
  """
  tiles,tile_bounds = self.tileslist(bbox, [zoomlevel],self.reader.tms_osm)
  grid = {}
  # for (z, x, y) in sorted(tiles,key=operator.itemgetter(0,1,2),reverse=True):
  for (z, x, y) in tiles:
   if not grid.get(y):
    grid[y] = []
   grid[y].append(x)
  sortedgrid = []
  for y in sorted(grid.keys(),reverse=not self.reader.tms_osm):
   sortedgrid.append([(x, y) for x in sorted(grid[y])])
  return sortedgrid,tile_bounds

 def export_image(self, bbox, zoomlevel, imagepath):
  """
  Writes to ``imagepath`` the tiles for the specified bounding box and zoomlevel.
  """
  assert has_pil, _("Cannot export image without python PIL")
  grid,tile_bounds = self.grid_tiles(bbox, zoomlevel)
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
  if imagepath.endswith(".tif") or imagepath.endswith(".tiff"):
   # http://effbot.org/imagingbook/pil-index.htm#appendixes
   # Packbits, LZW, or JPEG
   # In the current version, PIL always writes uncompressed TIFF files.
   image_gdal="gdal_input.tif"
   result.save(image_gdal, format="TIFF", compression="JPEG")
   self.geotif_image(tile_bounds,(widthpix,heightpix),imagepath,image_gdal)
  else:
   if imagepath.endswith(".jpg") or imagepath.endswith(".jpeg"):
    # IOError: encoder error -2 when writing image file
    result.save(imagepath, format="JPEG", quality=int(self.jpg_quality), optimize=True, progressive=False)
   elif  imagepath.endswith(".png") :
    result.save(imagepath, format="PNG",optimize=True)
   else:
    result.save(imagepath)
   logger.info(_("-I-> export_image: Save resulting image to '%s' - bounds[%s]") % (imagepath,tile_bounds))

 def geotif_image(self, tile_bounds, image_bounds, imagepath,image_gdal):
  """
  Writes to ``imagepath`` the tiles for the specified bounding box and zoomlevel.
  """
  i_srid=3857
  s_srid="WGS 84 / Pseudo-Mercator"
  # i_srid=3395
  # s_srid="WGS 84 / World Mercator"
  # 4326 Wsg84
  # Upper Left  (  -8.4375000,  77.1571625) (  8d26'15.00"W, 77d 9'25.79"N)
  # Lower Left  (  -8.4375000,  35.4606700) (  8d26'15.00"W, 35d27'38.41"N)
  # Upper Right (  80.1562500,  77.1571625) ( 80d 9'22.50"E, 77d 9'25.79"N)
  # Lower Right (  80.1562500,  35.4606700) ( 80d 9'22.50"E, 35d27'38.41"N)
  # Center      (  35.8593750,  56.3089162) ( 35d51'33.75"E, 56d18'32.10"N)
  # 3857 'WGS 84 / Pseudo-Mercator'
  # Upper Left  ( -939258.204,13932330.020) (  8d26'15.00"W, 77d 9'25.79"N)
  # Lower Left  ( -939258.204, 4226661.916) (  8d26'15.00"W, 35d27'38.41"N)
  # Upper Right ( 8922952.934,13932330.020) ( 80d 9'22.50"E, 77d 9'25.79"N)
  # Lower Right ( 8922952.934, 4226661.916) ( 80d 9'22.50"E, 35d27'38.41"N)
  # Center      ( 3991847.365, 9079495.968) ( 35d51'33.75"E, 62d54'54.84"N)
  # 3395 'WGS 84 / World Mercator'
  # Upper Left  ( -939258.204,13932330.020) (  8d26'15.00"W, 77d14'24.81"N)
  # Lower Left  ( -939258.204, 4226661.916) (  8d26'15.00"W, 35d38'33.56"N)
  # Upper Right ( 8922952.934,13932330.020) ( 80d 9'22.50"E, 77d14'24.81"N)
  # Lower Right ( 8922952.934, 4226661.916) ( 80d 9'22.50"E, 35d38'33.56"N)
  # Center      ( 3991847.365, 9079495.968) ( 35d51'33.75"E, 63d 4'14.87"N)
  bounds_west,bounds_south,bounds_east,bounds_north=tile_bounds
  bounds_wsg84="bounds_wsg84: %f,%f,%f,%f"% (bounds_west,bounds_south,bounds_east,bounds_north)
  mercator = GlobalMercator()
  tile_bounds=mercator.BoundsToMeters(tile_bounds)
  mbtiles_name="";
  mbtiles_description=""
  s_TIFFTAG_DOCUMENTNAME=""
  s_TIFFTAG_IMAGEDESCRIPTION=""
  s_TIFFTAG_SOFTWARE=""
  s_TIFFTAG_DATETIME=""
  s_TIFFTAG_ARTIST=""
  s_TIFFTAG_HOSTCOMPUTER=""
  s_TIFFTAG_COPYRIGHT=""
  if self.metadata_input:
   metadata=dict(self.metadata_input)
   mbtiles_name=metadata.get('name','')
   mbtiles_description=metadata.get('description','')
  if self._metadata:
   for metadata_list in self._metadata:
    metadata=dict(metadata_list[0])
    mbtiles_name=metadata.get('name',mbtiles_name)
    mbtiles_description=metadata.get('description',mbtiles_description)
    s_TIFFTAG_DOCUMENTNAME=metadata.get('TIFFTAG_DOCUMENTNAME',mbtiles_name)
    s_TIFFTAG_IMAGEDESCRIPTION=metadata.get('TIFFTAG_IMAGEDESCRIPTION',mbtiles_description)
    s_TIFFTAG_SOFTWARE=metadata.get('TIFFTAG_SOFTWARE','')
    s_TIFFTAG_DATETIME=metadata.get('TIFFTAG_DATETIME','')
    s_TIFFTAG_ARTIST=metadata.get('TIFFTAG_ARTIST','')
    s_TIFFTAG_HOSTCOMPUTER=metadata.get('TIFFTAG_HOSTCOMPUTER','')
    s_TIFFTAG_COPYRIGHT=metadata.get('TIFFTAG_COPYRIGHT','')
  if s_TIFFTAG_DOCUMENTNAME == "":
   s_TIFFTAG_DOCUMENTNAME=mbtiles_name
  if s_TIFFTAG_IMAGEDESCRIPTION == "":
   s_TIFFTAG_IMAGEDESCRIPTION=mbtiles_description
  tiff_metadata=[]
  if s_TIFFTAG_DOCUMENTNAME != "":
   tiff_metadata.append(('TIFFTAG_DOCUMENTNAME',s_TIFFTAG_DOCUMENTNAME))
  if s_TIFFTAG_IMAGEDESCRIPTION != "":
   tiff_metadata.append(('TIFFTAG_IMAGEDESCRIPTION',s_TIFFTAG_IMAGEDESCRIPTION))
  if s_TIFFTAG_SOFTWARE != "":
   tiff_metadata.append(('TIFFTAG_SOFTWARE',s_TIFFTAG_SOFTWARE))
  else:
   tiff_metadata.append(('TIFFTAG_SOFTWARE',bounds_wsg84))
  if s_TIFFTAG_DATETIME != "":
   tiff_metadata.append(('TIFFTAG_DATETIME',s_TIFFTAG_DATETIME))
  if s_TIFFTAG_ARTIST != "":
   tiff_metadata.append(('TIFFTAG_ARTIST',s_TIFFTAG_ARTIST))
  if s_TIFFTAG_HOSTCOMPUTER != "":
   tiff_metadata.append(('TIFFTAG_HOSTCOMPUTER',s_TIFFTAG_HOSTCOMPUTER))
  if s_TIFFTAG_COPYRIGHT != "":
   tiff_metadata.append(('TIFFTAG_COPYRIGHT',s_TIFFTAG_COPYRIGHT))
  # this assumes the projection is Geographic lat/lon WGS 84
  xmin,ymin,xmax,ymax=tile_bounds
  image_width,image_height=image_bounds
  # Upper Left  (   20800.000,   22000.000)
  # Lower Right (   24000.000,   19600.000)
  # Size is 15118, 11339
  # (24000-20800)/15118 = 3200 = 0,21166821 [xres]
  # (19600-22000)/11339 = 2400 =  −0,211658876 [yres]
  # geo_transform = (20800.0, 0.2116682100807, 0.0, 22000.0, 0.0, -0.21165887644413)
  geo_transform = [xmin, (xmax-xmin)/image_width, 0, ymax, 0, (ymin-ymax)/image_height ]
  spatial_projection = osr.SpatialReference()
  spatial_projection.ImportFromEPSG(i_srid)
  logger.info(_("-I-> geotif_image: Saveing as GeoTiff - image[%s] compression[%s]") % (imagepath,self.tiff_compression))
  image_dataset = gdal.Open(image_gdal, gdal.GA_Update )
  image_dataset.SetProjection(spatial_projection.ExportToWkt())
  image_dataset.SetGeoTransform(geo_transform)
  driver = gdal.GetDriverByName("GTiff")
  output_dataset = driver.CreateCopy(imagepath,image_dataset, 0, self.tiff_compression )
  if tiff_metadata:
   logger.info(_("-I-> geotif_image: tiff_metadata[%s]") % tiff_metadata)
   output_dataset.SetMetadata(dict(tiff_metadata))
  # Once we're done, close properly the dataset
  output_dataset = None
  image_dataset = None
  os.remove(image_gdal)
  logger.info(_("-I-> geotif_image: Saved resulting image to '%s' as GeoTiff- bounds[%s]") % (imagepath,tile_bounds))


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

 def tile(self, z, x, y_tms):
  """
  Download the specified tile from `tiles_url`
  """
  logger.debug(_("Download tile %s") % ((z, x, y_tms),))
  # Render each keyword in URL ({s}, {x}, {y}, {z}, {size} ... )
  size = self.tilesize
  s = self.tiles_subdomains[(x + y_tms) % len(self.tiles_subdomains)];
  y_osm = (2**int(z) - 1) - int(y_tms)
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
  self.wmsParams[projectionKey] = GlobalMercator.WSG84

 def tile(self, z, x, y_tms):
  logger.debug(_("Request WMS tile %s") % ((z, x, y_tms),))
  y_osm = (2**int(z) - 1) - int(y_tms)
  mercator = GlobalMercator(True,self.tilesize,[z])
  bbox = mercator.tile_bbox((z, x, y_osm))
  # bbox = mercator.project(bbox[:2]) + mercator.project(bbox[2:])
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
  except (AssertionError, IOError),e:
   # BBOX parameter's minimum Y is greater than the maximum Y
   # srs is not permitted: EPSG:3857
   logger.error(_("WMS request URL: Error %s:") % e.args[0])
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
  tile_name = "%s%s" % (y, self.extension)
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
