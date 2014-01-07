#!/usr/bin/env python
# -*- coding: utf-8 -*-
# TODO: Cleaning the code, refactoring before 1.0 publishing

import os, sys
import webbrowser
import wx
import wx.lib.delayedresult as delayedresult # threading in wx

import config
import icons
import wizard
import widgets
import gdalpreprocess

from bug_report import do_bug_report_dialog
import wxgdal2mbtiles as wxgdal

# TODO: GetText
_ = lambda s: s

GENERIC_GUI_EVENT = wx.NewEventType()
EVT_GENERIC_GUI = wx.PyEventBinder(GENERIC_GUI_EVENT, 0)

class GenericGuiEvent(wx.PyEvent):
 def __init__(self, data=None):
  wx.PyEvent.__init__(self)
  self.SetEventType(GENERIC_GUI_EVENT)
  self.data = data

class MainFrame(wx.Frame):
 def __init__(self, *args, **kwds):

  #spath = wx.StandardPaths.Get()
  #config.documentsdir = spath.GetDocumentsDir()
  config.documentsdir = os.path.expanduser('~')

  self.abortEvent = delayedresult.AbortEvent()
  self.jobID = 0
  self.rendering = False
  self.resume = False

  kwds["style"] = wx.DEFAULT_FRAME_STYLE
  wx.Frame.__init__(self, *args, **kwds)

  # self.panel_0 = wx.Panel(self, -1)
  # self.panel_1 = wx.Panel(self.panel_0, -1)
  self.panel_1 = wx.Panel(self, -1)
  self.panel_2 = wx.Panel(self.panel_1, -1)

  # Menu Bar
  self.main_frame_menubar = wx.MenuBar()

  menu = wx.Menu()
  item = menu.Append(wx.NewId(), _("Insert &raster map files"))
  self.Bind(wx.EVT_MENU, self.OnOpen, item)
  self.bug_report = menu.Append(wx.NewId(), _("Send a &bug report"))
  self.Bind(wx.EVT_MENU, self.OnBugReport, self.bug_report)
  #item = menu.Append(wx.ID_PREFERENCES, _("&Preferences"))
  #self.Bind(wx.EVT_MENU, self.OnPrefs, item)
  item = menu.Append(wx.ID_EXIT, _("&Exit"))
  self.Bind(wx.EVT_MENU, self.OnQuit, item)
  self.main_frame_menubar.Append(menu, _("&File"))

  menu = wx.Menu()
  item = menu.Append(wx.ID_HELP, _("Online &Help && FAQ"))
  self.Bind(wx.EVT_MENU, self.OnHelp, item)
  item = menu.Append(wx.NewId(), _("MapMbTiles User &Group"))
  self.Bind(wx.EVT_MENU, self.OnGroupWeb, item)
  item = menu.Append(wx.NewId(), _("Donation"))
  self.Bind(wx.EVT_MENU, self.OnDonate, item)
  item = menu.Append(wx.NewId(), _("Project &website"))
  self.Bind(wx.EVT_MENU, self.OnProjectWeb, item)
  item = menu.Append(wx.ID_ABOUT, _("&About"))
  self.Bind(wx.EVT_MENU, self.OnAbout, item)
  self.main_frame_menubar.Append(menu, _("&Help"))

  self.Bind(EVT_GENERIC_GUI, self.updateRenderText)
  self.Bind(wxgdal.EVT_UPDATE_PROGRESS, self.updateProgress)

  self.SetMenuBar(self.main_frame_menubar)

  # Events
  self.Bind(wx.EVT_CLOSE, self.OnQuit)
  #self.Bind(wx.EVT_RADIOBUTTON, self.OnRadio)

  # Menu Bar end
  self.bitmap_1 = wx.StaticBitmap(self, -1, icons.getIcon140Bitmap()) # wx.Bitmap("../resources/icon140.png", wx.BITMAP_TYPE_ANY))
  self.steplabel = []
  self.steplabel.append(wx.StaticText(self, -1, _("Tile Properties")))
  self.steplabel.append(wx.StaticText(self, -1, _("Tile Profile")))
  self.steplabel.append(wx.StaticText(self, -1, _("Source Data Files")))
  self.steplabel.append(wx.StaticText(self, -1, _("Spatial Reference")))
  self.steplabel.append(wx.StaticText(self, -1, _("Tile Details"))) # Zoom levels, PNG/JPEG, Tile adressing, Postprocessing?
  self.steplabel.append(wx.StaticText(self, -1, _("Destination"))) # Directory / database
  self.steplabel.append(wx.StaticText(self, -1, _("Viewers")))
  self.steplabel.append(wx.StaticText(self, -1, _("Viewer Details")))
  self.steplabel.append(wx.StaticText(self, -1, _("Rendering")))

  self.label_10 = wx.StaticText(self, -1, _("MapMbTiles - MbTiles / Tile Generator"))

  self.label_8 = wx.StaticText(self, -1, _("https://github.com/mj10777/mapmbtiles"))
  self.label_9 = wx.StaticText(self, -1, _(u"(C) 2014 Mark Johnson"))

  self.button_back = wx.Button(self, -1, _("Go &Back"))
  self.Bind(wx.EVT_BUTTON, self.OnBack, self.button_back)
  self.button_continue = wx.Button(self, -1, _("&Continue"))
  self.Bind(wx.EVT_BUTTON, self.OnContinue, self.button_continue)

  #self.html = widgets.SpatialReferencePanel(self.panel_2, -1)
  self.html = wizard.WizardHtmlWindow(self.panel_2, -1)
  self.html.SetBorders(0)
  self.html.SetMinSize((500, 385))

  # Set the first step of the wizard..
  self.SetStep(wizard.WizardHtmlWindow.i_step_properties)

  self.__set_properties()
  self.__do_layout()

 def __set_properties(self):
  self.SetTitle(_("MapMbTiles - MbTiles / Tile Generator"))
  if sys.platform in ['win32','win64']:
   icon = wx.Icon( sys.executable, wx.BITMAP_TYPE_ICO )
   self.SetIcon( icon )
  if sys.platform.startswith('linux'):
   self.SetIcon( icons.getIconIcon() )
  self.SetBackgroundColour(wx.Colour(253, 253, 253))
  for label in self.steplabel[1:]:
   label.Enable(False)
  self.label_10.SetForegroundColour(wx.Colour(220, 83, 9))
  self.label_10.SetFont(wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD, 0, ""))
  self.panel_2.SetBackgroundColour(wx.Colour(255, 255, 255))
  # self.panel_0.SetBackgroundColour(wx.Colour(192, 192, 192))
  self.panel_1.SetBackgroundColour(wx.Colour(192, 192, 192))
  self.label_8.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, ""))
  self.label_9.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, ""))
  self.button_back.Enable(False)
  self.button_continue.SetDefault()

 def __do_layout(self):
  sizer_1 = wx.BoxSizer(wx.VERTICAL)
  sizer_3 = wx.BoxSizer(wx.HORIZONTAL)
  sizer_5 = wx.BoxSizer(wx.VERTICAL)
  sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
  sizer_6 = wx.BoxSizer(wx.VERTICAL)
  sizer_9 = wx.BoxSizer(wx.HORIZONTAL)
  sizer_10 = wx.BoxSizer(wx.HORIZONTAL)
  sizer_4 = wx.BoxSizer(wx.VERTICAL)
  sizer_8 = wx.BoxSizer(wx.VERTICAL)
  sizer_4.Add(self.bitmap_1, 0, wx.BOTTOM, 25)
  for label in self.steplabel:
   sizer_8.Add(label, 0, wx.ALL, 5)
  sizer_4.Add(sizer_8, 1, wx.LEFT|wx.EXPAND, 15)
  sizer_2.Add(sizer_4, 0, wx.RIGHT|wx.EXPAND, 5)
  sizer_6.Add(self.label_10, 0, wx.TOP|wx.BOTTOM, 15)
  sizer_10.Add(self.html, 1, wx.ALL|wx.EXPAND, 30)
  self.panel_2.SetSizer(sizer_10)
  sizer_9.Add(self.panel_2, 1, wx.ALL|wx.EXPAND, 2)
  # self.panel_0.SetSizer(sizer_9)
  # sizer_6.Add(self.panel_0, 1, wx.ALL|wx.EXPAND, 2)
  self.panel_1.SetSizer(sizer_9)
  sizer_6.Add(self.panel_1, 1, wx.ALL|wx.EXPAND, 2)
  sizer_2.Add(sizer_6, 1, wx.LEFT|wx.RIGHT|wx.EXPAND, 10)
  sizer_1.Add(sizer_2, 1, wx.LEFT|wx.RIGHT|wx.TOP|wx.EXPAND, 15)
  sizer_5.Add(self.label_8, 0, 0, 0)
  sizer_5.Add(self.label_9, 0, 0, 0)
  sizer_3.Add(sizer_5, 1, wx.EXPAND, 0)
  sizer_3.Add(self.button_back, 0, wx.RIGHT, 10)
  sizer_3.Add(self.button_continue, 0, wx.RIGHT, 10)
  sizer_1.Add(sizer_3, 0, wx.ALL|wx.EXPAND, 15)
  self.SetSizer(sizer_1)
  sizer_1.SetSizeHints(self)
  #sizer_1.Fit(self)
  self.Layout()
  self.Centre(wx.BOTH)
  #self.SetMinSize((700, 500))

 def OnQuit(self,Event):
  self.Destroy()

 def OnAbout(self, event):
  # First we create and fill the info object
  info = wx.AboutDialogInfo()
  info.Name = _("MapMbTiles")
  info.Version = config.version
  info.Copyright = u"(C) 2014 Mark Johnson"
  info.Description = _("""MapMbTiles is a powerful tool for online map publishing and generation of raster overlay mashups.
Your geodata are transformed to the tiles compatible with Google Maps and Earth - ready for uploading to your webserver.""")

  #info.WebSite = ("https://github.com/mj10777/mapmbtiles", "MapMbTiles HomePage")
  #info.Developers = [ "Joe Programmer", "Jane Coder", "Vippy the Mascot" ]
  #info.License = """New BSD License"""

  # Then we call wx.AboutBox giving it that info object
  wx.AboutBox(info)

 def OnProjectWeb(self, event):
  webbrowser.open_new(_("http://www.mapmbtiles.org"))

 def OnDonate(self, event):
  webbrowser.open_new(config.DONATE_URL)

 def OnGroupWeb(self, event):
  webbrowser.open_new(_("http://groups.google.com/group/mapmbtiles"))

 def OnHelp(self, event):
  webbrowser.open_new(_("http://help.mapmbtiles.org"))

 def OnOpen(self, event):
  dlg = wx.FileDialog(
   self, message=_("Choose a file"),
   defaultDir=config.documentsdir,
   defaultFile="",
   wildcard=config.supportedfiles,
   style=wx.OPEN | wx.MULTIPLE #| wx.CHANGE_DIR
   )

  # Show the dialog and retrieve the user response. If it is the OK response,
  # process the data.
  if dlg.ShowModal() == wx.ID_OK:
   paths = dlg.GetPaths()

   bad_paths = [path for path in paths if not os.access(path, os.R_OK)]
   if len(bad_paths) > 0:
    wx.MessageBox(_("MapMbTiles doesn't have permission to read the following files:\n\n") + "\n".join(bad_paths),
     _("Bad permissions"), wx.ICON_ERROR)
    return
   else:
    for path in paths:
     try:
      self._add(path)
     except gdalpreprocess.PreprocessError, e:
      wx.MessageBox(str(e), _("Can't add a file"), wx.ICON_ERROR)
      return

  step = self.html.GetActiveStep()
  self.SetStep(wizard.WizardHtmlWindow.i_step_input)

 def OnBugReport(self, event):
  if len(config.files) == 0:
   wx.MessageBox(_("""
The bug report feature is intended for reporting issues with specific \
input files. You have not selected any yet."""), _("No input files selected"), wx.ICON_INFORMATION)
   return

  do_bug_report_dialog(self, "", self.html.GetActiveStep())


 def OnPrefs(self, event):
  dlg = wx.MessageDialog(self, _("This would be an preferences Dialog\n")+
          _("If there were any preferences to set.\n"),
        _("Preferences"), wx.OK | wx.ICON_INFORMATION)
  dlg.ShowModal()
  dlg.Destroy()

 def SetLableUpTo(self, step):
  if step > len(self.steplabel):
   step = len(self.steplabel)
  for i in range(0,step):
   self.steplabel[i].Enable()
  for i in range(step, len(self.steplabel)):
   self.steplabel[i].Enable(False)

 def SetStep(self, step):
  # 1 - 7 normal, step 8 - before render + rendering + resume, step 9 - final
  self.SetLableUpTo(step)

  # Label of the buttons
  if step < wizard.WizardHtmlWindow.i_step_rendering:
   self.button_continue.SetLabel(_("&Continue"))
   self.button_back.SetLabel(_("Go &Back"))
  if step == wizard.WizardHtmlWindow.i_step_rendering:
   if self.rendering:
    self.button_continue.SetLabel(_("&Render"))
    self.button_back.SetLabel(_("&Stop"))
   elif self.resume:
    self.button_continue.SetLabel(_("&Resume"))
    self.button_back.SetLabel(_("Go &Back"))
   else:
    self.button_continue.SetLabel(_("&Render"))
    self.button_back.SetLabel(_("Go &Back"))
  if step > wizard.WizardHtmlWindow.i_step_rendering:
   self.button_back.SetLabel(_("Go &Back"))
   self.button_continue.SetLabel(_("Exit"))
   self.button_continue.Enable()

  # Enable / Disable
  if step == wizard.WizardHtmlWindow.i_step_properties:
   self.button_back.Enable(False)
  else:
   self.button_back.Enable()

  if step == wizard.WizardHtmlWindow.i_step_rendering and self.rendering:
   self.button_continue.Enable(False)
  else:
   self.button_continue.Enable()

  oldstep = self.html.GetActiveStep()
  if oldstep != step:
   self.html.SaveStep(oldstep)
   self.html.SetStep(step)

 def OnBack(self, event):
  step = self.html.GetActiveStep()
  if step > 0 and not self.rendering:
   new_step=step-1
   if new_step == wizard.WizardHtmlWindow.i_step_profile and config.mbtiles:
    new_step=wizard.WizardHtmlWindow.i_step_properties
   self.SetStep( new_step )
  elif self.rendering:
   self._renderstop()
   self.SetStep( step )

 def OnContinue(self, event):
  # retrieve the active 'step' which has not been compleated/saved
  step = self.html.GetActiveStep()
  if step == wizard.WizardHtmlWindow.i_step_source:
   if len(config.files) == 0:
    wx.MessageBox(_("""You have to add some files for rendering"""), _("No files specified"), wx.ICON_ERROR)
    return
   if config.files[0][1] == '' and config.profile != 'raster':
    wx.MessageBox(_("""Sorry the file you have specified does not have georeference.\n\nClick on the 'Georeference' button and give a bounding box or \ncreate a world file (.wld) for the specified file."""), _("Missing georeference"), wx.ICON_ERROR)
    return
  if step == wizard.WizardHtmlWindow.i_step_spatial:
   self.html.SaveStep(wizard.WizardHtmlWindow.i_step_spatial)
   #print config.srs
   if config.files[0][1] != '':
    print type(config.srs)
    print config.srs
    srs = gdalpreprocess.SRSInput(config.srs)
    print srs
    if not srs:
     wx.MessageBox(_("""You have to specify reference system of your coordinates.\n\nTIP: for latitude/longitude in WGS84 you should type 'EPSG:4326'"""), _("Not valid spatial reference system"), wx.ICON_ERROR)
     return
    else:
     config.srs = srs
  if step == wizard.WizardHtmlWindow.i_step_output:
   self.html.SaveStep(wizard.WizardHtmlWindow.i_step_output)

   # If the user selected the output directory himself.
   if os.path.exists(config.outputdir):
    if not os.access(config.outputdir, os.W_OK):
     wx.MessageBox(_("The selected output directory '%s' is not writeable.") % config.outputdir,
      _("Bad permissions"), wx.ICON_ERROR)
     return
   # Default output directory on Windows and Mac.
   else:
    dirname = os.path.split(config.outputdir)[0]
    if not os.access(dirname, os.W_OK):
     wx.MessageBox(_("""The selected output directory '%s' can't be created, \
because its superdirectory '%s' is not writeable.""") % (config.outputdir, dirname),
      _("Bad permissions"), wx.ICON_ERROR)
     return

  if step == wizard.WizardHtmlWindow.i_step_properties:
   self.html.SaveStep(wizard.WizardHtmlWindow.i_step_properties)
   if config.mbtiles:
    step = wizard.WizardHtmlWindow.i_step_source-1 # Skip settings of the profile

  if step == wizard.WizardHtmlWindow.i_step_output and config.profile == 'gearth':
   self.html.SaveStep(wizard.WizardHtmlWindow.i_step_output)
   if config.format.startswith('garmin'):
    step = wizard.WizardHtmlWindow.i_step_viewer_properties # Skip settings of the viewers

  if step == wizard.WizardHtmlWindow.i_step_zoom and config.mbtiles:
   step = wizard.WizardHtmlWindow.i_step_viewers # Skip settings of the viewers

  if step == wizard.WizardHtmlWindow.i_step_rendering:
   self._renderstart()
   self.SetStep( wizard.WizardHtmlWindow.i_step_rendering )
  if step < wizard.WizardHtmlWindow.i_step_rendering: # maximum is 7 (now 8)
   self.SetStep( step + 1 )
  if step > wizard.WizardHtmlWindow.i_step_rendering:
   self.Destroy()

 def _add(self, filename):

  filename = filename.encode('utf8')

  if len(config.files) > 0:
   wx.MessageBox(_("""Unfortunately the merging of files is not yet implemented in the MapMbTiles GUI. Only the first file in the list is going to be rendered."""), _("Not yet implemented :-("), wx.ICON_ERROR)

  filerecord = gdalpreprocess.singlefile(filename)
  if filerecord:
   config.files = []
   config.files.append(filerecord)

 def _renderstop(self):

  self.g2t.stop()
  self.abortEvent.set()
  self.rendering = False
  self.resume = True
  self.html.UpdateRenderText(_("Rendering stopped !!!!"))
  self.html.StopThrobber()

 def _renderstart(self):
  self.abortEvent.clear()
  self.rendering = True
  self.html.UpdateRenderText(_("Started..."))
  self.html.StartThrobber()
  self.jobID += 1

  params = self.createParams()
  print "-"*20
  for p in params:
   print type(p), p

  delayedresult.startWorker(self._resultConsumer, self._resultProducer,
    wargs=(self.jobID,self.abortEvent, params), jobID=self.jobID)

 def createParams(self):

  params = ['--profile',config.profile if not config.format.startswith('garmin') else 'garmin',
   '--s_srs',config.srs,
   '--zoom',"%i-%i" % (config.tminz, config.tmaxz),
   '--title',config.title,
   '--copyright',config.copyright,
   '--tile-format', config.format if not config.format.startswith('garmin') else 'jpeg'
   ]
  viewer = 'none'
  if config.google:
   viewer = 'google'
  if config.openlayers:
   viewer = 'openlayers'
  if config.google and config.openlayers:
   viewer = 'all'
  params.extend(['--webviewer',viewer])
  if config.kml:
   params.append('--force-kml')
  if config.verbose:
   params.append('--verbose')
  if config.mbtiles:
   params.append('--mbtiles')
  if not config.tms_osm:
   params.append('--osm')
  if config.nodata:
   params.extend(['--srcnodata','%f,%f,%f' % config.nodata])

  if config.format.startswith('garmin'):
   params.extend(['--tilesize',config.format[6:]])

  if config.url:
   params.extend(['--url',config.url])
  if config.googlekey:
   params.extend(['--googlekey',config.googlekey])
  if config.yahookey:
   params.extend(['--yahookey',config.googlekey])

  # And finally the files
  params.append( config.files[0][2].encode('utf-8') )

  # and output directory
  params.append( config.outputdir )

  return params

 def updateRenderText(self, event):
  # do all of this stuff on the GUI thread
  self.html.UpdateRenderText(event.data)

 def updateProgress(self, event):
  # do all of this stuff on the GUI thread
  self.html.UpdateRenderProgress(event.progress)

 def _resultProducer(self, jobID, abortEvent, params):
  try:
   if config.resume and params[0] != '--resume':
    params.insert(0, '--resume')
   if self.resume and params[0] != '--resume':
    params.insert(0, '--resume')

   self.g2t = wxgdal.wxPPGDAL2MbTiles(params)
   self.g2t.set_event_handler(self)

   wx.PostEvent(self, GenericGuiEvent(_("Opening the input files")))
   self.g2t.open_input()
   # Opening and preprocessing of the input file

   if not self.g2t.stopped and not abortEvent():
    wx.PostEvent(self, GenericGuiEvent(_("Generating viewers and metadata")))
    # Generation of main metadata files and HTML viewers
    self.g2t.generate_metadata()

   if not self.g2t.stopped and not abortEvent():
    wx.PostEvent(self, GenericGuiEvent(_("Rendering the base tiles")))
    # Generation of the lowest tiles
    self.g2t.generate_base_tiles()

   if not self.g2t.stopped and not abortEvent():
    wx.PostEvent(self, GenericGuiEvent(_("Rendering the overview tiles in the pyramid")))
    # Generation of the overview tiles (higher in the pyramid)
    self.g2t.generate_overview_tiles()

   if not self.g2t.stopped and not abortEvent():
    wx.PostEvent(self, GenericGuiEvent(_("Generating KML")))
    # Generation of KML
    self.g2t.generate_kml()

  except Exception, e:
   self.g2t = e

 def _resultConsumer(self, delayedResult):
  jobID = delayedResult.getJobID()
  assert jobID == self.jobID
  result = delayedResult.get()

  if isinstance(self.g2t, Exception):
   self.rendering = False
   self.resume = False
   self.SetStep(wizard.WizardHtmlWindow.i_step_rendering)
   wx.PostEvent(self, GenericGuiEvent(_("Rendering error!")))
   self.html.StopThrobber()
   raise self.g2t

  elif not self.g2t.stopped:
   self.rendering = False
   self.resume = False
   self.SetStep(wizard.WizardHtmlWindow.i_step_rendering+1)


# end of class MainFrame
