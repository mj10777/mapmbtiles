#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging,os
from mapmbtiles import MBTilesBuilder
# .bashrc
# export PYTHONPATH=/usr/lib/mapmbtiles:$PYTHONPATH

logging.basicConfig(level=logging.DEBUG)
output_directory="output"
# i_parm=0: run programm ; = 1 show info only and return
i_parm=0
i_min_level=2
i_max_level=2
#----------------------------------------------------------------------------------
for i_loop in range(i_min_level,i_max_level+1):
 if i_loop == 0:
  # this will create a 'mbtiles_output.mbtiles' in the directory where called
  # using: 'http://{s}.tile.openstreetmap.org/{z}/{x}/{y_osm}.png'
  # as default: 'jpg' images in the mbtiles files are stored as 'jpg' with 75% quality
  # - the recieved png will be converted to jpg
  mb_step1 = MBTilesBuilder(cache=False)
  mb_step1.add_coverage(bbox=(-180.0, -90.0, 180.0, 90.0), zoomlevels=[0,1])
  # use u'äöüßÄÖÜ' syntax in insure unicode when inserting into sqlite3
  metadata_list = [
          (u'name',u'World OpenStreetMap'),
          (u'description',u'World OpenStreet Map with jpg tiles'),
          (u'center',u'13.3777065575123,52.5162690144797,1'),
         ]
  mb_step1.add_metadata(metadata_list) 
  # with 'False' we are telling MBTilesBuilder to exit if the file exists
  # with 'True' we are telling MBTilesBuilder to use an existing mbtiles file
  # i_parm=0: run programm ; = 1 show info only and return
  # - if no parmameters are given: 'False,0' is assumed
  # i_parm=1
  mb_step1.run(False,i_parm)
  del mb_step1
#----------------------------------------------------------------------------------
 if i_loop == 1:
  # set the optput file name
  Output_filepath="%s/World_OpenStreetMap_png.mbtiles" % output_directory
  print  "Loop: ",i_loop,"\nOutput: ",Output_filepath  
  # using: 'http://{s}.tile.openstreetmap.org/{z}/{x}/{y_osm}.png'
  # as default: 'jpg' images in the mbtiles files are stored as 'jpg' with 75% quality
  # - here we will override this default and force the storeage og 'png'
  # mbtiles only supports 'jpg' or 'png'
  mb_step2 = MBTilesBuilder(mbtiles_output=Output_filepath,tile_format="png")
  mb_step2.add_coverage(bbox=(-180.0, -90.0, 180.0, 90.0), zoomlevels=[0,1,2])
  # use u'äöüßÄÖÜ' syntax in insure unicode when inserting into sqlite3
  metadata_list = [
          (u'name',u'World OpenStreetMap'),
          (u'description',u'World OpenStreet Map with png tiles'),
          (u'center',u'13.3777065575123,52.5162690144797,1'),
         ]
  mb_step2.add_metadata(metadata_list)
  # with 'False' we are telling MBTilesBuilder to exit if the file exists
  # with 'True' we are telling MBTilesBuilder to use an existing mbtiles file
  # i_parm=0: run programm ; = 1 show info only and return
  # - if no parmameters are given: 'False,0' is assumed
  # i_parm=1
  mb_step2.run(False,i_parm)
  del mb_step2
#----------------------------------------------------------------------------------
 if i_loop == 2:
  # set the optput file name
  Output_filepath="%s/Berlin_Strassennetz.mbtiles" % output_directory
  print  "Loop: ",i_loop,"\nOutput: ",Output_filepath  
  # http://fbinter.stadt-berlin.de/fb/wms/senstadt/k_vms_detailnetz_wms_spatial?service=WMS&request=GetMap&version=1.1.1&layers=0,1,2,3,4&styles=visual&srs=EPSG:4326&format=image/jpeg&width=3840&height=2880&bbox=13.33,52.5,13.35,52.6
  # as default: 'jpg' images in the mbtiles files are stored as 'jpg' with 75% quality
  # - here we will override this default and force the storeage og 'png'
  # mbtiles only supports 'jpg' or 'png'
  s_wms_server="http://fbinter.stadt-berlin.de/fb/wms/senstadt/k_vms_detailnetz_wms_spatial"
  s_wms_layers="0,1,2,3,4"
  parm_wms_options=dict(format="image/jpeg") 
  mb_step3 = MBTilesBuilder(mbtiles_output=Output_filepath,wms_server=s_wms_server,wms_layers=[s_wms_layers],wms_options=parm_wms_options)
  mb_step3.add_coverage(bbox=(13.0928,52.3454,13.7501,52.6688), zoomlevels=[13,14,15,16])
  # use u'äöüßÄÖÜ' syntax in insure unicode when inserting into sqlite3
  metadata_list = [
          (u'name',u'Straßennetz von Berlin'),
          (u'description',u'Detailliertes Straßennetz von Berlin zu verkehrlichen Zwecken, enthält über das klassifizierte Straßennetz hinaus weitere Straßen und Wege.'),
          (u'center',u'13.3777065575123,52.5162690144797,16'),
         ]
  mb_step3.add_metadata(metadata_list)
  # with 'False' we are telling MBTilesBuilder to exit if the file exists
  # with 'True' we are telling MBTilesBuilder to use an existing mbtiles file
  # i_parm=0: run programm ; = 1 show info only and return
  # - if no parmameters are given: 'False,0' is assumed
  # i_parm=1
  mb_step3.run(False,i_parm)
  del mb_step3
 #----------------------------------------------------------------------------------

