A PostGIS importer for CityGML data
==========================

citygml2pgsql converts buildings found in a CityGML file to MultiPolygon insert statements aimed at PosgresSQL/PostGIS.


Schema
======
```
CREATE TABLE public.buildings (
    id text NOT NULL,
    filename text,
    roof public.geometry(MultiPolygonZ,3857),
    wall public.geometry(MultiPolygonZ,3857),
    ground public.geometry(MultiPolygonZ,3857),
    footprint public.geometry(MultiPolygon,3857),
    bl character(2)
);


CREATE TABLE public.imports (
    filename text,
    md5sum character(32),
    count integer,
    bundesland text
);
```


Usage
======
Configure database, column names and target SRS in `config.yaml`.

Then, run

```
uv run citygml2pgsql <input_folder> <input_srs> <lod> --bundesland bl
# e.g.
uv run citygml2pgsql data/gml_files_bw/ 25832 lod2 --bundesland bw
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

