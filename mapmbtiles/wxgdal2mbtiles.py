import wx
import pp

from time import sleep
from thread import allocate_lock
from Queue import Empty

from gdal2mbtiles import GDAL2MbTiles

# TODO: GetText
from config import _

UPDATE_PROGRESS_EVENT = wx.NewEventType()
EVT_UPDATE_PROGRESS = wx.PyEventBinder(UPDATE_PROGRESS_EVENT, 0)


class UpdateProgressEvent(wx.PyEvent):
 def __init__(self, progress):
  wx.PyEvent.__init__(self)
  self.SetEventType(UPDATE_PROGRESS_EVENT)
  self.progress = progress


def process_tiles(args, method):

 """Process base or overview tiles."""

 try:
  g2t = mapmbtiles.gdal2mbtiles.GDAL2MbTiles(args, is_subprocess=True)
  print "UpdateProgressEvent :process_tiles(",method,")"
  g2t.open_input()

  if method == "base":
   g2t.generate_base_tiles()
  elif method == "overview":
   g2t.generate_overview_tiles()
 except Exception, e:
  error = e
 else:
  error = None

 sys.stderr.write("EXIT\n")
 sys.stderr.flush()

 return error


class PPGDAL2MbTiles(GDAL2MbTiles):

 def __init__(self, args, gdal_cache=None):
  GDAL2MbTiles.__init__(self, args, gdalcache=gdal_cache)
  self.__pp_args = args
  self.__pp_job_server = pp.Server(ncpus=1)
  self.__pp_lock = allocate_lock()

 def generate_base_tiles(self):
  self.__pp_run("base")

 def generate_overview_tiles(self):
  self.__pp_run("overview")

 def stop(self):
  GDAL2MbTiles.stop(self)
  self.__pp_lock.acquire()
  self.__pp_lock.release()

 def __pp_run(self, method):
  self.__pp_lock.acquire()

  job = self.__pp_job_server.submit(process_tiles, args=(self.__pp_args, method),
     modules=("mapmbtiles.gdal2mbtiles", "sys"))

  progress = 0.0

  while not job.wait(0):
   try:
    for i in xrange(self.__pp_job_server.msg_que.qsize()):
     msg = self.__pp_job_server.msg_que.get_nowait()
     try:
      progress = float(msg)
     except ValueError:
      pass
   except Empty:
    pass

   sleep(0.128)

   self.progressbar(progress)

   if self.stopped:
    self.__pp_job_server.destroy()
    self.__pp_lock.release()
    return

  error = job()

  if error is not None:
   self.__pp_job_server.destroy()
   self.__pp_lock.release()
   self.error(str(error))
   return

  # Don't leave unprocessed messages in queue.
  try:
   while True:
    self.__pp_job_server.msg_que.get_nowait()
  except Empty:
   pass

  self.progressbar(1.0)

  self.__pp_lock.release()


def wxGDAL2MbTilesFactory(super_klass):

 """Return subclass of GDAL2MbTiles-like super_klass with code for GUI added.

 The reason behind this factory is that MapMbTiles GUI uses GDAL2MbTiles object
 to calculate some default values. Using parallel version for this is overkill
 and adding this code to both `GDAL2MbTiles' and `PPGDAL2MbTiles' is not DRY.
 """

 class klass(super_klass):

  """GUI capabilities for GDAL2MbTiles."""

  def __init__(self, *args, **kwargs):
   super_klass.__init__(self, *args, **kwargs)
   self.__wx_event_handler = None

  def error(self, msg, details = "" ):
   self.stop()

   if self.__wx_event_handler is not None:
    wx.PostEvent(self.__wx_event_handler, UpdateProgressEvent(0))

   raise Exception(msg)

  def set_event_handler(self, event_handler):
   self.__wx_event_handler = event_handler

  def progressbar(self, complete=0.0):
   if self.__wx_event_handler is not None:
    wx.PostEvent(self.__wx_event_handler, UpdateProgressEvent(int(complete*100)))

 return klass


wxGDAL2MbTiles = wxGDAL2MbTilesFactory(GDAL2MbTiles)
wxPPGDAL2MbTiles = wxGDAL2MbTilesFactory(PPGDAL2MbTiles)

