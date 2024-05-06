A PostGIS importer for CityGML data
==========================

citygml2pgsql converts buildings found in a CityGML file to MultiPolygon insert statements aimed at PosgresSQL/PostGIS.


Schema
======
```
CREATE TABLE buildings (id TEXT PRIMARY KEY, filename TEXT, lod2 GEOMETRY(MultipolygonZ, 3857));
CREATE TABLE imports (filename TEXT, md5sum CHAR(32), count INTEGER);
```


Usage
======
Configure database, column names and target SRS in `config.yaml`.

Then, run

```
python citygml2pgsql.py <input_folder> <input_srs> <lod> 
# e.g.
python citygml2pgsql.py data/gml_files/ 25832 lod2
```


Credits
=======

Our work was funded by BMBF Prototype Fund:

<a href="https://prototypefund.de/">
  <img src='https://github.com/open-pv/.github/assets/74312290/9dfa1ce4-adaf-4638-9cbc-e519b033331b' width='300'>
</a>

Forked from https://gitlab.com/Oslandia/citygml2pgsql. Original Credits:

> This plugin has been developed by Oslandia ( http://www.oslandia.com ).
>
> First release was funded by European Union (FEDER related to the e-PLU project) and by Oslandia.

License
=======

This work is free software and licenced under the MIT licence.
See LICENSE file.

