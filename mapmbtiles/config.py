version = "1.0 beta2"

tile_profile = 'mbtiles'
y_type = 'tms'
profile = 'mercator'
files = [ ]
# files.append("/media/gb_1500/maps/map_tiler/testimage/1930.Berlin_Spandau_Uebersichstskarte.100000.1200.3068.tif")
nodata = None
srs = "";
customsrs = ""
srsformat = 0
tminz = 0
tmaxz = 0
format = False
resume = False
verbose = True
mbtiles = True
mbtiles_todisk = False
mbtiles_fromdisk = False
tms_osm = True
kml = False
outputdir = None
url = "http://" # TODO: Do not submit this to the command-line
viewer_google = False
viewer_openlayers = False
title = ""
copyright = "&copy;"
googlekey = ""
yahookey = ""

documentsdir = ""

bboxgeoref = False

DONATE_URL = "https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=1806586"

# TODO: GetText
_ = lambda s: s

# WellKnownGeogCS
wellknowngeogcs = ['WGS84','WGS72','NAD27','NAD83']

# Subset of the GDAL supported file formats...
supportedfiles =  _("Supported raster files")+"|*.tif;*.tiff;*.kap;*.img;*.sid;*.ecw;*.jp2;*.j2k;*.nitf;*.h1;*.h2;*.hd;*.hdr;*.cit;*.rgb;*.raw;*.blx;*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.wms;*.vrt|" + \
        _("TIFF / BigTIFF / GeoTIFF (.tif)")+"|*.tif;*.tiff|" + \
        _("BSB Nautical Chart Format (.kap)")+"|*.kap|" + \
        _("JPEG2000 - JPEG 2000 (.jp2, .j2k)")+"|*.jp2;*.j2k|" + \
        _("MrSID - Multi-resolution Seamless Image Database (.sid)")+"|*.sid|" + \
        _("ECW - ERMapper Compressed Wavelets (.ecw)")+"|*.ecw|" + \
        _("HFA - Erdas Imagine Images (.img)")+"|*.img|" + \
        _("NITF - National Imagery Transmission Format (.nitf)")+"|*.nitf|" + \
        _("NDF - NLAPS Data Format (.h1,.h2,.hd)")+"|*.h1;*.h2;*.hd|" + \
        _("MFF - Vexcel MFF Raster (.hdr)")+"|*.hdr|" + \
        _("INGR - Intergraph Raster Format (.cit,.rgb,..)")+"|*.cit;*.rgb|" + \
        _("EIR -- Erdas Imagine Raw (.raw)")+"|*.raw|" + \
        _("BLX -- Magellan BLX Topo File Format (.blx)")+"|*.blx|" + \
        _("JPEG - Joint Photographic Experts Group JFIF (.jpg)")+"|*.jpg;*.jpeg|" + \
        _("PNG - Portable Network Graphics (.png)")+"|*.png|" + \
        _("GIF - Graphics Interchange Format (.gif)")+"|*.gif|" + \
        _("BMP - Microsoft Windows Device Independent Bitmap (.bmp)")+"|*.bmp|" + \
        _("WMS - GDAL driver for OGC Web Map Server (.wms)")+"|*.wms|" + \
        _("VRT - GDAL Virtual Raster (.vrt)")+"|*.vrt|" + \
        _("All files (*.*)")+"|*.*"

s = """
srsFormatList = ['format automatically detected',
        'WKT - Well Known Text definition',
        'ESRI WKT - Well Known Text definition',
        'EPSG number',
        'EPSGA number',
        'Proj.4 definition'
]
"""

srsFormatList = [
_('Custom definition of the system (WKT, Proj.4,..)'),
_('WGS84 - Latitude and longitude (geodetic)'),
_('Universal Transverse Mercator - UTM (projected)'),
_('Specify the id-number from the EPSG/ESRI database'),
_('Search the coordinate system by name'),
]

srsFormatListLocal = [
_('SRSCustom0'),_("SRSDefinition0"),
_('SRSCustom1'),_("SRSDefinition1"),
_('SRSCustom2'),_("SRSDefinition2"),
_('SRSCustom3'),_("SRSDefinition3"),
_('SRSCustom4'),_("SRSDefinition4"),
_('SRSCustom5'),_("SRSDefinition5"),
_('SRSCustom6'),_("SRSDefinition6"),
_('SRSCustom7'),_("SRSDefinition7"),
_('SRSCustom8'),_("SRSDefinition8"),
_('SRSCustom9'),_("SRSDefinition9")
]

#English-speaking coordinate systems defaults:
# 'OSGB 1936 / British National Grid (projected)'
# 'NZMG - New Zealand Map Grid'
# ''

#French-speaking coordinate systems defaults:
# Lambert

#German-speaking coordinate systems defaults:
# ...

s = """
#A = wx.PySimpleApp()
#A.SetAppName(VENDOR_NAME)

datadir = wx.StandardPaths.Get().GetUserLocalDataDir()
if not os.path.isdir(datadir):
    os.mkdir(datadir)
f = wx.FileConfig(localFilename=os.path.join(datadir,'MapMbTiles.cfg'))

f.SetPath("APath")
print f.Read("Key")
f.Write("Key", "Value")
f.Flush()
"""

epsg4326 = """GEOGCS["WGS 84",
    DATUM["WGS_1984",
        SPHEROID["WGS 84",6378137,298.257223563,
            AUTHORITY["EPSG","7030"]],
        AUTHORITY["EPSG","6326"]],
    PRIMEM["Greenwich",0,
        AUTHORITY["EPSG","8901"]],
    UNIT["degree",0.01745329251994328,
        AUTHORITY["EPSG","9122"]],
    AUTHORITY["EPSG","4326"]]"""
