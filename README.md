mapmbtiles
==========

Map MbTiles / Tile  Generator (Based on MapTiler 2009 version)


***

* the 'Map Tile Cutter' is based on the original work of:
    *  Klokan Petr Pridal `klokan.petr.pridal@gmail.com`
    *  the original project source can be found at `http://code.google.com/p/maptiler`
       * the source code used here was taken from the `maptiler_1.0.beta2_all.deb`
       *  to my knowlage the support for this project has been disscontinued in its Open-Source form.

* some of the Mbtiles creation logic was based on :
    *  the original project source can be found at `https://github.com/mapbox/mbutil/blob/master/mbutil/util.py`

* some of the Mbtiles funtionality :
    *  the original project source can be found at `https://github.com/makinacorpus/landez`
 

***

The main goal was to adapt the `gdal2tiles.py` to also support the creation of a mbtiles Database
    * the basic functionality has otherwise not been changed
    * `gdal2tiles.py` has been renamed to `gdal2mbtiles.py` to avoud conficts with the original gdal version

The created mbtiles Databases are base on the same logic used in the geopaparrazi project:
    * [https://github.com/geopaparazzi/geopaparazzi/wiki/mbtiles-Implementation]
    * it used `tiles` as a view and not a table
    * it will check for `blank` images (all pixels have the same RGB value) and store this only onece

When install on linux, a 'soft-link'  called 'gdal2mbtiles' will be created
    * this can be called with the same paramaters as `gdal2tiles.py`
    * when called with `--mbtiles` the [output] parameter will be used as the file-name for mbtiles
       * the extention `.mbtiles` should be used
       * the created tiles will then be stored in a mbtiles Database and NOT as a tile-directory
    * when called with `--mbtiles_from_disk` 
       * the [input_file] parameter will be used as the tile-directory
       * the [output] parameter will be used as the file-name for mbtiles
          * the tiles of the tile-directory will be imported into the mbtiles file
    * when called with `--mbtiles_to_disk` 
       * the [input_file] parameter will be used as the file-name for mbtiles
       * the [output] parameter will be used as the tile-directory
          * the tiles of the mbtiles will be exported into the tile-directory

***

In the `samples` directory, there are some python scripts thatuse this project when installed
* they are based on the functionality taken from the `Landez` project
   * importing all or a portion of one mbtiles to another
      * this can be used to `convert` a table based mbtiles to a `view` base mbtiles
         * this will also check for `blank` images
   * filling a mbtiles from a WMS-Server
   * exporting all or a portion of one mbtiles to a image
      * when `tif` is used, the result will be a geotif

The `Landez` project also supports other function, not yet tested:
* `Blend tiles together`
* `Merge multiple sources of tiles (URL, WMS, MBTiles, Mapnik stylesheet) together.`
* `Composite a WMS layer with OpenStreetMap using transparency`
* `Add post-processing filters`
* `Replace a specific color by transparent pixels`


***

Installing under linux:

* `deploy/linux/makedeb`
   * will create the `.deb` file
* `sudo dpkg -i mapmbtiles_1.0.beta2_all.deb`
   * will install the `.deb`

***

The original 'Map Tile Cutter' project also had routines for installing under `macosx` and `win32`
* these have remain unchanged and may or may not work

---

2014-02-28

---
