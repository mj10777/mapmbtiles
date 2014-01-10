#!/usr/bin/env python
import logging
from mapmbtiles import MBTilesBuilder
# .bashrc
# export PYTHONPATH=/usr/lib/mapmbtiles:$PYTHONPATH

logging.basicConfig(level=logging.DEBUG)
mb_step1 = MBTilesBuilder(cache=False)
mb_step1.add_coverage(bbox=(-180.0, -90.0, 180.0, 90.0), zoomlevels=[0, 1])
mb_step1.run()
