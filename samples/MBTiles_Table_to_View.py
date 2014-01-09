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
Source_filepath="%slidarplots.mbtiles" % input_directory
for i_loop in range(0,1):
 if i_loop == 0:
  Output_filepath="%slidarplots.mbtiles" % output_directory
 print  "Loop: ",i_loop,"\nSource: ",Source_filepath," \nOutput: ",Output_filepath   
 mb = MBTilesBuilder(mbtiles_input=Source_filepath, mbtiles_output=Output_filepath)
 # all of the 'metadata' of the 'input' will be placed in the 'output' mbtiles.db
 # for i_loop == 0 : the file will be rewritten and all metadata saved
 mb.run()


# mb.run_orig()


