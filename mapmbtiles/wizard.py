#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO: Cleaning the code, refactoring before 1.0 publishing

import os
import sys
import wx
import wx.html
import wx.lib.wxpTag
import webbrowser
import config
import icons

from wxgdal2mbtiles import wxGDAL2MbTiles

# TODO: GetText
_ = lambda s: s

class WizardHtmlWindow(wx.html.HtmlWindow):
 i_step_properties=1;
 i_step_profile=2;
 i_step_source=3;
 i_step_spatial=4;
 i_step_zoom=5;
 i_step_output=6;
 i_step_viewers=7;
 i_step_viewer_properties=8;
 i_step_rendering=9;
 def __init__(self, parent, id, pos=wx.DefaultPosition, size = wx.DefaultSize ):
  wx.html.HtmlWindow.__init__(self, parent, id, pos=pos, size=size, style=(wx.html.HW_NO_SELECTION |  wx.FULL_REPAINT_ON_RESIZE) )
  if "gtk2" in wx.PlatformInfo:
   self.SetStandardFonts()
  self.parent = parent
  self.step = 0

 def OnLinkClicked(self, linkinfo):
  webbrowser.open_new(linkinfo.GetHref())

 def GetActiveStep(self):
  return self.step

 def SetStep(self, step):
  self.step = step
  if step >= len(steps):
   config.rendering = False
   config.resume = False
   self.SetPage(step_final % (config.outputdir, config.outputdir) )
   return
  self.SetPage(steps[step])
  if step == self.i_step_properties:
   self.FindWindowByName(config.tile_profile).SetValue(1)
   self.FindWindowByName(config.y_type).SetValue(1)
   pass
  elif step == self.i_step_profile:
   self.FindWindowByName(config.profile).SetValue(1)
  elif step == self.i_step_source:
   self.FindWindowByName('verbose').SetValue(config.verbose)
   self.FindWindowByName('resume').SetValue(config.resume)
   pass
   #self.FindWindowByName('nodatapanel').SetColor(config.nodata)
  elif step == self.i_step_spatial:
   if not config.srs:
    config.customsrs = config.files[0][6]
    config.srs = config.customsrs
   if not config.srs and config.bboxgeoref:
    config.srsformat = 1
    config.srs = config.epsg4326
   self.FindWindowByName('srs').SetSelection(config.srsformat)
   self.FindWindowByName('srs').SetValue(config.srs)
  elif step == self.i_step_zoom:
   g2t = wxGDAL2MbTiles(['--profile',config.profile,'--s_srs', config.srs, str(config.files[0][2]) ])
   g2t.open_input()
   config.tminz = g2t.tminz
   config.tmaxz = g2t.tmaxz
   config.kml = g2t.kml
   del g2t

   self.FindWindowByName('tminz').SetValue(config.tminz)
   self.FindWindowByName('tmaxz').SetValue(config.tmaxz)
   if config.mbtiles:
    self.FindWindowByName('format').SetItems( [
      _("PNG - with transparency"),
      _("JPEG - smaller but without transparency")] )
    self.FindWindowByName('format').SetSelection(1) # jpg
    if config.outputdir is None:
     config.outputdir = os.path.dirname(config.files[0][0])
   else:
    if config.profile == 'gearth':
     self.FindWindowByName('format').SetItems( [
      _("PNG - with transparency"),
      _("JPEG - smaller but without transparency"),
      _("Hybrid JPEG+PNG - only for Google Earth"),
      _("Garmin Custom maps KMZ - 256 pixels"),
      _("Garmin Custom maps KMZ - 512 pixels"),
      _("Garmin Custom maps KMZ - 1024 pixels") ] )
    else:
     self.FindWindowByName('format').SetItems( [
      _("PNG - with transparency"),
      _("JPEG - smaller but without transparency"),
      _("Hybrid JPEG+PNG - only for Google Earth") ] )

    if not config.format and config.profile == 'gearth':
     self.FindWindowByName('format').SetSelection(2) # hybrid
    elif not config.format:
     self.FindWindowByName('format').SetSelection(0) # png
    else:
     self.FindWindowByName('format').SetSelection({'png':0,'jpeg':1,'hybrid':2,'garmin256':3,'garmin512':4,'garmin1024':5}[config.format])

   self.Refresh()
   self.Update()
  elif step == self.i_step_output:
   filename = config.files[0][0]

   # If this is the first time the user has gone this far,
   # we try to come up with sensible default output directory.
   if config.outputdir is None:
    input_dir = os.path.dirname(filename)
    # Implicitly we try to place it in the same directory in
    # which the input file is located. But if this is not possible,
    # we try to use the current directory.
    if os.access(input_dir, os.W_OK):
     base_dir = input_dir
    else:
     base_dir = os.getcwd()

    # Default name is the same as the input file without extensions.
    config.outputdir = os.path.join(base_dir, os.path.splitext(os.path.basename( filename ))[0] )

    # GTK2 doesn't allow to select nonexisting directories, so we have to make it exist.
    if sys.platform.startswith("linux"):
     if not os.path.exists(config.outputdir):
      try:
       os.makedirs(config.outputdir)
       config.gtk2_hack_directory = config.outputdir
      except Exception, e:
       config.outputdir = os.getcwd()
       config.gtk2_hack_directory = None

       # I hate it when I have to do this.
       wx.MessageBox(_("""\
We are terribly sorry for this error. It is a known issue stemming from the fact that we try hard to \
support all major software platforms -- Microsoft Windos, Mac OS X and UNIX systems. Unfortunately \
they don't have all the same capabilities.

You are processing file '%s' for which we can't provide default output directory, because both our \
options -- input file directory '%s' and your current working directory '%s' -- are not writeable. \
Please select the output directory on your own.""") % (filename, input_dir, os.getcwd()),
       _("Can't create default output directory"), wx.ICON_ERROR)
     else:
      config.gtk2_hack_directory = None

   self.FindWindowByName('outputdir').SetPath(config.outputdir)
  elif step == self.i_step_viewers:
   # GTK2 hack. See above.
   if sys.platform.startswith("linux") and config.gtk2_hack_directory is not None:
    if config.gtk2_hack_directory != config.outputdir:
     try:
      os.rmdir(config.gtk2_hack_directory)
     except:
      pass

   not_hybrid = config.format != 'hybrid'
   if config.profile=='tiles':
    if config.profile=='mercator':
     self.FindWindowByName('google').Enable(not_hybrid)
     self.FindWindowByName('openlayers').Enable(not_hybrid)
     self.FindWindowByName('kml').Enable(True)
    elif config.profile=='geodetic':
     self.FindWindowByName('google').Enable(False)
     self.FindWindowByName('openlayers').Enable(not_hybrid)
     self.FindWindowByName('kml').Enable(True)
    elif config.profile=='raster':
     self.FindWindowByName('google').Enable(False)
     self.FindWindowByName('openlayers').Enable(not_hybrid)
     if not config.kml:
      self.FindWindowByName('kml').Enable(False)
    elif config.profile=='gearth':
     self.FindWindowByName('google').Enable(False)
     self.FindWindowByName('openlayers').Enable(not_hybrid)
     self.FindWindowByName('kml').Enable(True)

   self.FindWindowByName('google').SetValue(config.google)
   self.FindWindowByName('openlayers').SetValue(config.openlayers)
   self.FindWindowByName('kml').SetValue(config.kml)

  elif step == self.i_step_viewer_properties:
   if config.mbtiles:
    s_title=os.path.splitext(os.path.basename( config.files[0][0]))
    # extract name portion [0] from tuple - extention = [1]
    s_title=s_title[0]
    config.copyright=s_title
    s_title=s_title.replace("."," ")
    s_title=s_title.replace("_"," ")
    config.title=s_title;
    self.FindWindowByName('title').SetValue(config.title)
    self.FindWindowByName('copyright').SetValue(config.copyright)
    self.FindWindowByName('googlekey').Enable(False)
    self.FindWindowByName('yahookey').Enable(False)
   else:
    config.title = os.path.basename( config.files[0][0] )
    self.FindWindowByName('title').SetValue(config.title)
    self.FindWindowByName('copyright').SetValue(config.copyright)
    self.FindWindowByName('googlekey').SetValue(config.googlekey)
    self.FindWindowByName('yahookey').SetValue(config.yahookey)

 def SaveStep(self, step):
  if step == self.i_step_properties:
   if self.FindWindowByName('mbtiles').GetValue():
    config.mbtiles = True
   else:
    config.mbtiles = False
   if self.FindWindowByName('tms').GetValue():
    config.tms_osm = True
   else:
    config.tms_osm = False
  elif step == self.i_step_profile:
   # Profile
   if self.FindWindowByName('mercator').GetValue():
    config.profile = 'mercator'
   elif self.FindWindowByName('geodetic').GetValue():
    config.profile = 'geodetic'
   elif self.FindWindowByName('raster').GetValue():
    config.profile = 'raster'
   elif self.FindWindowByName('gearth').GetValue():
    config.profile = 'gearth'
   print config.profile
  elif step == self.i_step_source:
   # Files + Nodata
   print config.files
   config.nodata = self.FindWindowByName('nodatapanel').GetColor()
   config.verbose = self.FindWindowByName('verbose').GetValue()
   config.resume = self.FindWindowByName('resume').GetValue()
   if config.verbose:
    print("Verbose in Terminal: ",config.verbose)
   if config.verbose:
    print("Resume: ",config.resume)
   print config.nodata
  elif step == self.i_step_spatial:
   #config.oldsrs = config.srs
   config.srs = self.FindWindowByName('srs').GetValue().encode('ascii','ignore').strip()
   config.srsformat = self.FindWindowByName('srs').GetSelection()
   print config.srs
  elif step == self.i_step_zoom:
   config.tminz = int(self.FindWindowByName('tminz').GetValue())
   config.tmaxz = int(self.FindWindowByName('tmaxz').GetValue())

   format = self.FindWindowByName('format').GetCurrentSelection()
   config.format = ('png','jpeg','hybrid','garmin256','garmin512','garmin1024')[format]

   if config.format != 'hybrid':
    config.google = config.profile == 'mercator'
    config.openlayers = True
   else:
    config.google = False
    config.openlayers = False
   config.kml = config.profile in ('gearth', 'geodetic')
   config.google = False
   config.openlayers = False
   print config.tminz
   print config.tmaxz
   print config.format
  elif step == self.i_step_output:
   config.outputdir = self.FindWindowByName('outputdir').GetPath().encode('utf8')
   config.url = self.FindWindowByName('url').GetValue()
   if config.url == 'http://':
    config.url = ''
   print config.url
  elif step == self.i_step_viewers:
   config.google = self.FindWindowByName('google').GetValue()
   config.openlayers = self.FindWindowByName('openlayers').GetValue()
   config.kml = self.FindWindowByName('kml').GetValue()
   print config.google
   print config.openlayers
   print config.kml
  elif step == self.i_step_viewer_properties:
   config.title = self.FindWindowByName('title').GetValue().encode('utf8')
   if not config.title:
    config.title = os.path.basename( config.files[0][0] ).encode('utf8')
   config.copyright = self.FindWindowByName('copyright').GetValue().encode('utf8')
   config.googlekey = self.FindWindowByName('googlekey').GetValue().encode('utf8')
   config.yahookey = self.FindWindowByName('yahookey').GetValue().encode('utf8')
   print config.title
   print config.copyright
   print config.googlekey
   print config.yahookey

 def UpdateRenderProgress(self, complete):
  if self.step != len(steps) - 1:
   print _("Nothing to update - progressbar not displayed")
   print _("Nothing to update - progressbar not displayed")
   return
  else:
   progressbar = self.FindWindowByName('progressbar')
   progressbar.SetValue(complete)

 def UpdateRenderText(self, text):
  if self.step != len(steps) - 1:
   print _("Nothing to update - progresstext not displayed")
   return
  else:
   progresstext = self.FindWindowByName('progresstext')
   progresstext.SetLabel(text)
   self.Layout()
   self.Refresh()

 def StartThrobber(self):
  self.FindWindowByName('throbber').Start()
  self.FindWindowByName('throbber').ToggleOverlay(False)

 def StopThrobber(self):
  self.FindWindowByName('throbber').Stop()
  self.FindWindowByName('throbber').ToggleOverlay(True)

step_properties = "<h3>"+_("Selection of the tile properties")+'''</h3>
 <p>
 <font color="#DC5309" size="large"><b>'''+_("Would you like a mbtiles or tiles to be created?")+'''</b></font>
 <p>
 <font size="-1">
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("mbtiles file")+'''">
     <param name="name" value="mbtiles">
     <param name="style" value="wx.RB_GROUP">
 </wxp>
 <blockquote>
 '''+_("Mbtiles file as created to be used in geoaparazzi, based on the mbtiles specfication. (")+'''
 <a href="https://github.com/geopaparazzi/geopaparazzi/wiki/mbtiles-Implementation/">'''+_("Geopaparazzi mbtiles-Implementation")+'''</a>.)
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test" >
     <param name="label" value="'''+_("tile directory")+'''">
     <param name="name" value="tiles">
 </wxp>
 <blockquote>
 '''+_('Tiles created for Web-Applications.')+'''
 </blockquote>
 <p>
 <font color="#DC5309" size="large"><b>'''+_("Would you like TMS or OSM y position nubbering to be created?")+'''</b></font>
 <p>
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("TMS y Numbering (South to North)")+'''">
     <param name="name" value="tms">
     <param name="style" value="wx.RB_GROUP">
 </wxp>
 <blockquote>
 '''+_("TMS Tile numbering for y position - South to North (")+'''<a href="http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification#Tile_Resources">'''+_("Tile Map Service Specification")+'''</a>)
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test" >
     <param name="label" value="'''+_("Slippy map y Numbering (OSM) (North to South)")+'''">
     <param name="name" value="osm">
 </wxp>
 <blockquote>
 '''+_("Tile numbering for y position as used in Open Street Map ,Slippy map tilenames - North to South (")+'''<a href="http://wiki.openstreetmap.org/wiki/Slippy_map_tilenames">'''+_("Slippy Map Tilenames")+'''</a>)
 </blockquote>
 </font>'''

step_profile = "<h3>"+_("Selection of the tile profile")+'''</h3>
 '''+_("MapMbTiles generates tiles for fast online map publishing.")+'''
 <p>
 <font color="#DC5309" size="large"><b>'''+_("What kind of tiles would you like to generate?")+'''</b></font>
 <p>
 <font size="-1">
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("Google Maps compatible (Spherical Mercator)")+'''">
     <param name="name" value="mercator">
 </wxp>
 <blockquote>
 '''+_("Mercator tiles compatible with Google, Yahoo or Bing maps and OpenStreetMap. Suitable for mashups and overlay with these popular interactive maps.")+'''
 <a href="https://github.com/mj10777/mapmbtilesgoogle-maps-coordinate-system-projection-epsg-900913-3785/">'''+_("More info")+'''</a>.
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("Google Earth (KML SuperOverlay)")+'''">
     <param name="name" value="gearth">
 </wxp>
 <blockquote>
 '''+_('Tiles and KML metadata for 3D vizualization in Google Earth desktop application or in the web browser plugin.')+'''
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("WGS84 Plate Caree (Geodetic)")+'''">
     <param name="name" value="geodetic">
 </wxp>
 <blockquote>
 '''+_('Compatible with most existing WMS servers, with the OpenLayers base map, Google Earth and other applications using WGS84 coordinates (<a href="http://www.spatialreference.org/ref/epsg/4326/">EPSG:4326</a>).')+'''
 <a href="https://github.com/mj10777/mapmbtilesgoogle-maps-coordinate-system-projection-epsg-900913-3785/">'''+'''</a>.
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test">
     <param name="label" value="'''+_("Image Based Tiles (Raster)")+'''">
     <param name="name" value="raster">
 </wxp>
 <blockquote>
 '''+_("Tiles based on the dimensions of the picture in pixels (width and height). Stand-alone presentation even for images without georeference.")+'''
 </blockquote>
 </font>'''

step_source = '''<h3>'''+_("Source data files")+'''</h3>
 '''+_("Please choose the raster files of the maps you would like to publish.")+'''
  <wxp module="wx" class="CheckBox" name="test"><param name="name" value="verbose"><param name="label" value="'''+("Verbose in Terminal")+'''"></wxp>
 <br>
 <wxp module="wx" class="CheckBox" name="test"><param name="name" value="resume"><param name="label" value="'''+("Resume Tile genration if output exists")+'''"></wxp>
 <br>
 <font color="#DC5309" size="large"><b>'''+_("Input raster map files:")+'''</b></font>
 <!--
 <wxp module="wx" class="ListCtrl" name="listctrl" height="250" width="100%">
     <param name="name" value="listctrl">
 </wxp>
 -->
 <wxp module="mapmbtiles.widgets" class="FilePanel" name="test" height="230" width=100%>
 <param name="name" value="filepanel"></wxp>
 <p>
 <wxp module="mapmbtiles.widgets" class="NodataPanel" name="test" height="30" width=100%>
 <param name="name" value="nodatapanel"></wxp>'''

step_spatial = '''<h3>'''+_("Spatial reference system (SRS)")+'''</h3>
 '''+_('It is necessary to know which coordinate system (Spatial Reference System) is used for georeferencing of the input files. More info in the <a href="http://help.mapmbtiles.org/coordinates/">MapMbTiles help</a>.')+'''
 <p>
 <font color="#DC5309" size="large"><b>'''+_("What is the Spatial Reference System used in your files?")+'''</b></font>
 <p>
 <wxp module="mapmbtiles.widgets" class="SpatialReferencePanel" name="test" height="260" width=100%>
 <param name="name" value="srs">
 </wxp>'''

step_zoom = '''<h3>'''+_("Details about the tile pyramid")+'''</h3> <!-- Zoom levels, Tile Format (PNG/JPEG) & Addressing, PostProcessing -->
 '''+_("In this step you should specify the details related to rendered tile pyramid.")+'''
 '''+_("<!-- file format and convention for tile addressing (names of the tile files) which you would like to use. -->")+'''
 <p>
 <font color="#DC5309" size="large"><b>'''+_("Zoom levels to generate:")+'''</b></font>
 <p>
 '''+_("Minimum zoom:")+''' <wxp module="wx" class="SpinCtrl" name="test"><param name="value" value="0"><param name="name" value="tminz"></wxp> &nbsp;
 '''+_("Maximum zoom:")+''' <wxp module="wx" class="SpinCtrl" name="test"><param name="value" value="0"><param name="name" value="tmaxz"></wxp>
 <br>
 <font size="-1">
 '''+_("Note: The selected zoom levels are calculated from your input data and should be OK in most cases.")+'''
 </font>
 <p>
 <font color="#DC5309" size="large"><b>'''+_('Please choose a file format')+'''</b></font>
 <font size="-1">
 <p>
 <wxp module="wx" class="Choice" name="test">
  <param name="name" value="format">
  <param name="choices" value="(\''''+_("PNG - with transparency")+"','"+_("JPEG - smaller but without transparency")+"','"+_("Hybrid JPEG+PNG - only for Google Earth")+'''\')">
 </wxp>
 <p>
 <font size="-1">
 '''+_('Note: We recommend to <a href="http://blog.klokan.cz/2008/11/png-palette-with-variable-alpha-small.html">postprocess the produced PNG tiles with the PNGNQ utility</a>.')+'''
 </font>
 <!--
 <p>
 <font color="#DC5309" size="large"><b>Tile adressing:</b></font>
 <p>
 <font size="-1">
 <wxp module="wx" class="RadioButton" name="test"><param name="name" value="raster"><param name="label" value="OSGeo TMS - Tile Map Service"></wxp>
 <blockquote>
 Tile addressing used in open-source software tools. Info: <a href="http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification">Tile Map Service</a>.
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test"><param name="name" value="raster"><param name="label" value="Google - Native Google Adressing"></wxp>
 <blockquote>
 Native tile addressing used by Google Maps API. Info: <a href="http://code.google.com/apis/maps/documentation/overlays.html#Google_Maps_Coordinates">Google Maps Coordinates</a>
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test"><param name="name" value="raster"><param name="label" value="Microsoft - QuadTree"></wxp>
 <blockquote>
 Tile addressing used in Microsoft products. Info: <a href="http://msdn.microsoft.com/en-us/library/bb259689.aspx">Virtal Earth Tile System</a>
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test"><param name="name" value="raster"><param name="label" value="Zoomify"></wxp>
 <blockquote>
 Format of tiles used in popular web viewer. Info: <a href="http://www.zoomify.com">Zoomify.com</a>.
 </blockquote>
 <wxp module="wx" class="RadioButton" name="test"><param name="name" value="raster"><param name="label" value="Deep Zoom"></wxp>
 <blockquote>
 Tile format used in Deep Zoom viewers of the Microsoft SeaDragon project.
 </blockquote>
 </font>
 -->
 '''

step_output = '''<h3>'''+_("Destination folder and address")+'''</h3>
'''+_("Please select a directory where the generated tiles should be saved. Similarly you can specify the Internet address where will you publish the map.")+'''
<p>
<font color="#DC5309" size="large"><b>'''+_("Where to save the generated tiles?")+'''</b></font>
<p>
'''+_("Result directory:")+'''<br/>
<wxp module="wx" class="DirPickerCtrl" name="outputdir" width="100%" height="30"><param name="name" value="outputdir"></wxp>
<p>
<font color="#DC5309" size="large"><b>'''+_("The Internet address (URL) for publishing the map:")+'''</b></font>
<p>
'''+_("Destination URL:")+'''<br/>
<wxp module="wx" class="TextCtrl" name="test" width="100%"><param name="name" value="url"><param name="value" value="http://"></wxp>
<p>
<font size="-1">
'''+_("Note: You should specify the URL if you need to generate the correct KML for Google Earth.")+'''
</font>'''

step_viewers = '''<h3>'''+_("Selection of the viewers")+'''</h3>
'''+_("MapMbTiles can also generate simple web viewers for presenting the tiles as a map overlay. You can use these viewers as a base for your mashups. Similarly it is possible to generate KML files for Google Earth.")+'''
<p>
<font color="#DC5309" size="large"><b>'''+_("What viewers should be generated?")+'''</b></font>
<p>
<font size="-1">
<wxp module="wx" class="CheckBox" name="test"><param name="name" value="google"><param name="label" value="'''+_("Google Maps")+'''"></wxp>
<blockquote>
'''+_("Overlay presentation of your maps on top of standard Google Maps layers. If KML is generated then the Google Earth Plugin is used as well.")+'''
</blockquote>
<wxp module="wx" class="CheckBox" name="test"><param name="name" value="openlayers"><param name="label" value="'''+_("OpenLayers")+'''"></wxp>
<blockquote>
'''+_('Overlay of Google Maps, Virtual Earth, Yahoo Maps, OpenStreetMap and OpenAerialMap, WMS and WFS layers and another sources available in the open-source project <a href="http://www.openlayers.org/">OpenLayers</a>.')+'''
</blockquote>
<wxp module="wx" class="CheckBox" name="test"><param name="name" value="kml"><param name="label" value="'''+("Google Earth (KML SuperOverlay)")+'''"></wxp>
<blockquote>
'''+_("If this option is selected then metadata for Google Earth is generated for the tile tree. It means you can display the tiles as an overlay of the virtual 3D world of the Google Earth desktop application or browser plug-in.")+'''
</blockquote>
</font>'''

step_viewer_properties = '''<h3>'''+_("Details for generating the viewers")+'''</h3>
'''+_("Please add information related to the selected viewers.")+'''
<p>
<font color="#DC5309" size="large"><b>'''+_("Info about the map")+'''</b></font>
<p>
'''+_("Title of the map - for mbtiles: 'name':")+'''<br/>
<wxp module="wx" class="TextCtrl" name="test" width="100%"><param name="name" value="title"></wxp>
<p>
'''+_("Copyright notice (optional) - for mbtiles 'description:")+'''<br/>
<wxp module="wx" class="TextCtrl" name="test" width="100%"><param name="name" value="copyright"></wxp>
<p>
<font color="#DC5309" size="large"><b>'''+_("The API keys for online maps API viewers")+'''</b></font>
<p>
'''+_("Google Maps API key (optional):")+'''<br/>
<wxp module="wx" class="TextCtrl" name="test" width="100%"><param name="name" value="googlekey"></wxp>
<font size="-1">
'''+_('Note: You can get it <a href="http://code.google.com/apis/maps/signup.html">online at this address</a>.')+'''
</font>
<p>
'''+_("Yahoo Application ID key (optional):")+'''<br/>
<wxp module="wx" class="TextCtrl" name="test" width="100%"><param name="name" value="yahookey"></wxp>
<font size="-1">
'''+_('Note: You can get it <a href="http://developer.yahoo.com/wsregapp/">at this webpage</a>.')+'''
</font>'''

step_rendering = '''<h3>'''+_("Tile rendering")+'''</h3>
'''+_("Now you can start the rendering of the map tiles. It can be a time consuming process especially for large datasets... so be patient please.")+'''
<p>
<font color="#DC5309" size="large"><b>'''+_("Rendering progress:")+'''</b></font>
<p>
<wxp module="wx" class="Gauge" name="g1" width="100%">
    <param name="name" value="progressbar">
</wxp>
<center>
<wxp module="wx" class="StaticText" name="progresstext" width="450">
    <param name="style" value="wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE">
    <param name="name" value="progresstext">
    <param name="label" value="'''+_("Click on the 'Render' button to start the rendering...")+'''">
</wxp>
<p>
<wxp module="mapmbtiles.widgets" class="Throbber" name="throbber" width="16" height="16">
    <param name="name" value="throbber">
</wxp>
</center>
<font size="-1">
<p>&nbsp;
<br>'''+_("Thank you for using MapMbTiles application.")+" "+_('This is an open-source project - you can help us to make it better.')+" "+_('Join the <a href="http://groups.google.com/group/mapmbtiles">MapMbTiles User Group</a> to speak with other MapMbTiles users and tell us about the maps you are publishing!')+" "+_('You can also <a href="http://mapmbtiles.uservoice.com/">suggest improvements</a> or <a href="http://code.google.com/p/mapmbtiles/issues/list">report bugs</a>.')+'''
<p>
'''+_("Please consider")+' <b><a href="'+config.DONATE_URL+'">'+_("donation via PayPal or Credit Card.")+ "</a></b> "+_("We welcome contribution to the source code, help with documentation, localization or with user support.")+" "+_('Thanks belongs to <a href="http://help.mapmbtiles.org/credits/">those who have already helped</a>!')+'''
<p>
'''+_('Authors of this utility provide <b><a href="http://www.mapmbtiles.com/">commercial support</a></b> related to the map tile rendering, geodata processing and customization of open-source GIS tools. We have developed also a <b><a href="http://www.mapmbtiles.com/">fast parallelized utility</a></b> for efficient tile rendering on Multi-Core processors and on clusters like Amazon EC2.</font>')

# step9 - step8 with Resume button

# step10:
step_final = '''<h3>'''+_("Your rendering task is finished!")+'''</h3>
'''+_("Thank you for using this software. Now you can see the results. If you upload the directory with tiles to the Internet your map is published!")+'''
<p>
<font color="#DC5309" size="large"><b>'''+_("Available results:")+'''</b></font>
<p>
'''+_("The generated tiles and also the viewers are available in the output directory:")+'''
<p>
<center>
<b><a href="file://%s">%s</a></b><br>'''+_("(click to open)")+'''
</center>
<!--
<ul>
<li>Open the <a href="">Google Maps presentation</a>
<li>Open the <a href="">OpenLayers presentation</a>
</ul>
-->
'''
steps = ['NULL',step_properties, step_profile, step_source, step_spatial, step_zoom,step_output, step_viewers, step_viewer_properties, step_rendering ]


