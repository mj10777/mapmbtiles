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

import sys
import os
import math
import sqlite3
import logging

from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from io import BytesIO

from globalmercator import GlobalMercator

try:
 from PIL import Image
 import numpy
 from xml.etree import ElementTree
 import osgeo.gdal_array as gdalarray
except:
 # 'antialias' resampling is not available
 pass

# =============================================================================
# =============================================================================
# UPDATE map SET tile_id = replace(tile_id, '.None', '.tms');
# UPDATE images SET tile_id = replace(tile_id, '.None', '.tms');
# =============================================================================
# base on code faound at. https://github.com/mapbox/mbutil/blob/master/mbutil/util.py
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
  self.mbtiles_format='jpg'
  self.mbtiles_minzoom='0'
  self.mbtiles_maxzoom='22'
  self.mbtiles_bounds="%f,%f,%f,%f"% (self.bounds_west,self.bounds_south,self.bounds_east,self.bounds_north)
  self.center_x=(self.bounds_east+self.bounds_west)/2
  self.center_y=(self.bounds_north+self.bounds_south)/2
  self.mbtiles_center="%f,%f,%s"%(self.center_x,self.center_y,self.default_zoom)
  print self.mbtiles_center

 def open_db(self,s_path_db,mbtiles_dir,mbtiles_format,s_y_type,verbose=False):
  self.mbtiles_dir=mbtiles_dir
  if s_y_type == "osm":
   self.s_y_type=s_y_type
   tms_osm=True
  self.mbtiles_format=mbtiles_format
  self.verbose=verbose
  self.s_path_db = s_path_db
  self.verbose=True
  # setting a default value
  self.mbtiles_name=os.path.splitext(os.path.basename( self.s_path_db ))[0]
  self.mbtiles_description=self.mbtiles_name.replace("."," ")
  self.mbtiles_description=self.mbtiles_description.replace("_"," ")
  db_create=os.path.exists(self.s_path_db)
  self.sqlite3_connection=self.mbtiles_connect(s_path_db)
  self.mbtiles_cursor = self.sqlite3_connection.cursor()
  self.optimize_connection()
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
  self.metadata=dict(self.mbtiles_cursor.execute('SELECT name, value FROM metadata;').fetchall())
  if self.metadata:
   self.mbtiles_name=self.metadata.get('name')
   self.mbtiles_description=self.metadata.get('description')
   self.mbtiles_type=self.metadata.get('type')
   self.mbtiles_version=self.metadata.get('version')
   self.s_y_type = self.metadata.get('tile_row_type')
   self.mbtiles_format=self.metadata.get('format')
   self.mbtiles_bounds=self.metadata.get('bounds')
   self.mbtiles_center=self.metadata.get('center')
   self.mbtiles_minzoom=self.metadata.get('minzoom')
   self.mbtiles_maxzoom=self.metadata.get('maxzoom')
   print self.mbtiles_center
   sa_center=self.mbtiles_center.split(",")
   if len(sa_center) == 3:
    self.center_x=float(sa_center[0])
    self.center_y=float(sa_center[1])
    self.default_zoom=int(sa_center[2])
   sa_bounds=self.mbtiles_bounds.split(",")
   if len(sa_bounds) == 4:
    self.bounds_west=float(sa_bounds[0])
    self.bounds_east=float(sa_bounds[2])
    self.bounds_north=float(sa_bounds[3])
    self.bounds_south=float(sa_bounds[1])
  return self.metadata

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

 def insert_metadata(self,values_list):
  if self.verbose:
   print "MbTiles : insert_metadata:",values_list
  try:
   self.mbtiles_cursor.executemany("INSERT OR REPLACE INTO metadata VALUES(?,?)",values_list)
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
  if not  os.path.exists(directory_path):
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
  if self.mbtiles_description != '':
   self.mbtiles_description=os.path.splitext(os.path.basename(directory_path))
   if self.mbtiles_name != '':
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
