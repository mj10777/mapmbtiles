#!/usr/bin/env python
import logging
from mapmbtiles import MBTilesBuilder
# .bashrc
# export PYTHONPATH=/usr/lib/mapmbtiles:$PYTHONPATH
    
logging.basicConfig(level=logging.DEBUG)
input_directory="source/"
output_directory="output/"
s_name="";
# zoom-levels 0-3
Source_filepath="%s1861_Mercator_World.mbtiles" % input_directory
for i_loop in range(0,3):
 if i_loop == 0:
  Output_filepath="%s1861_Mercator_World.mbtiles" % output_directory
 if i_loop == 1:  
  Output_filepath="%s1861_Mercator_Europe.mbtiles" % output_directory
 if i_loop == 2:  
  Output_filepath="%s1861_Mercator_Europe_Africa.mbtiles" % output_directory
 print  "Loop: ",i_loop,"\nSource: ",Source_filepath," \nOutput: ",Output_filepath   
 mb = MBTilesBuilder(mbtiles_input=Source_filepath, mbtiles_output=Output_filepath)
 # all of the 'metadata' of the 'input' will be placed in the 'output' mbtiles.db
 # for i_loop == 0 : the file will be rewritten and all metadata saved
 # for i_loop == 1 : the area of Europe will be extracted
 # for i_loop == 2 : the area of Europe and Africa will be extracted
 # when finished with the inserts, the  the min/max zoom_levels, bounds and center will be calculated and saved
 if i_loop == 1:  
  position_west=-8.0
  position_south=36.0
  position_east=80.0
  position_north=77.0
  mb.add_coverage(bbox=(position_west,position_south,position_east,position_north), zoomlevels=[3])
  # - the original 'name' and calulated center will be changed ; here 'Europe' and the Brandenburg Gate, Berlin as center
  metadata_list = [
         ('name', "1861 Mercator Europe"),
         ('center', "13.3777065575123,52.5162690144797,3"),
        ]
  mb.add_metadata(metadata_list)
 if i_loop == 2:
  position_west=-8.0
  position_south=36.0
  position_east=80.0
  position_north=77.0
  mb.add_coverage(bbox=(position_west,position_south,position_east,position_north),zoomlevels=[2,3])
  position_west=-32.0
  position_south=-37.0
  position_east=53.0
  position_north=36.0
  mb.add_coverage(bbox=(position_west,position_south,position_east,position_north),zoomlevels=[2,3])
  # - the original 'name' and calulated center will be changed ; here 'Europe/Africa' and Piazza della Signoria, Florence as center
  metadata_list = [
         ('name', "1861 Mercator Europe/Africa"),
         ('center', "11.255867505557262,43.76961577178412,3"), 
        ]
  mb.add_metadata(metadata_list) 
 mb.run()


# mb.run_orig()


