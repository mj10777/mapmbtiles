from distutils.core import setup
import os, sys
import glob

if sys.platform in ['win32','win64']:
 import py2exe
if sys.platform == 'darwin':
 import py2app

from mapmbtiles import version

setup(name='MapMbTiles',
      version=version,
      description = "MapMbTiles - Map Tile / MbTiles Generator",
      long_description= "MapMbTiles is a powerful tool for online map publishing and generation of map overlay mashups. Your geodata are transformed to the tiles compatible with Google Maps and Earth - ready for uploading to your webserver.",
      url='http://www.mapmbtiles.org/',
      author='Klokan Petr Pridal',
      author_email='klokan@klokan.cz',
      packages=['mapmbtiles'],
      scripts=['mapmbtiles.py'],
      windows=[ {'script':'mapmbtiles.py', "icon_resources": [(1, os.path.join('resources', 'mapmbtiles.ico'))] } ],
      app=['mapmbtiles.py'],
      data_files=[
        ('gdaldata', glob.glob('gdaldata/*.*')),
        ('gdalplugins', glob.glob('gdalplugins/*.*')),
        ('', glob.glob('*.dll'))
      ],
      options={'py2exe':{'packages':['mapmbtiles'],
                         'includes':['encodings','osgeo','osgeo.gdal','osgeo.osr'],
                         },
               'py2app':{'argv_emulation':True,
                         'iconfile':os.path.join('resources', 'mapmbtiles.icns'),
                         'packages':['mapmbtiles'],
                         'includes':['encodings'],
                         #'site_packages':True,
                         },
               },

)
