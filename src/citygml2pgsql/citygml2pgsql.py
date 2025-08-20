#!/usr/bin/python
# coding: utf-8

from lxml import etree
import yaml
import psycopg2
from psycopg2.extras import execute_batch
import argparse
from pathlib import Path
from tqdm import tqdm
import pypeln.process as pl
from munch import munchify
import shapely as shp

from .gml_utils import get_attrib_no_matter_the_namespace, gmlPolygon2wkt, md5sum


def insert_tuples(cursor, tuples, conf):
  execute_batch(
    cursor,
    f"INSERT INTO {conf.db.table} ({conf.columns.id}, {conf.columns.filename}, {conf.columns.roof}, {conf.columns.wall}, {conf.columns.ground}, {conf.columns.footprint}, bl) "
    f"VALUES (%(id)s, %(filename)s, "
    f"ST_Transform(%(roof)s, {conf.target_srs}), "
    f"ST_Transform(%(wall)s, {conf.target_srs}), "
    f"ST_Transform(%(ground)s, {conf.target_srs}), "
    f"ST_Transform(%(footprint)s, {conf.target_srs}), "
    f"%(bl)s) "
    f"ON CONFLICT ({conf.columns.id}) DO UPDATE SET "
    f"{conf.columns.roof}=EXCLUDED.{conf.columns.roof}, "
    f"{conf.columns.wall}=EXCLUDED.{conf.columns.wall}, "
    f"{conf.columns.ground}=EXCLUDED.{conf.columns.ground}, "
    f"{conf.columns.footprint}=EXCLUDED.{conf.columns.footprint}, "
    f"{conf.columns.filename}=EXCLUDED.{conf.columns.filename}, "
    f"bl=EXCLUDED.bl;",
    tuples,
  )


def citygml2pgsql(filename, conf, args):
  try:
    root = etree.parse(filename)
  except etree.XMLSyntaxError as e:
    print(f"XML Error in {filename}!")
    print(e)
    return 0

  n_buildings = 0

  with psycopg2.connect(
    database=conf.db.database, host=conf.db.host, port=conf.db.port
  ) as conn:
    cur = conn.cursor()

    # generate a multipolygon surface per building part
    geometry_types = [
      "{*}" + args.lod + geom_type
      for geom_type in ["Solid", "MultiSurface", "CompositeSurface"]
    ]
    # special treatment for Mecklenburg-Vorpommern... :)
    geometry_types += ["{*}BuildingGeometry3DLoD" + args.lod[-1]]
    tuples = []
    for building in root.iter("{*}Building"):
      building_id = get_attrib_no_matter_the_namespace(building, "id")
      polygons = {}
      polygons_wkt = {}
      for surf_type in ["Wall", "Roof", "Ground"]:
        polygons[surf_type] = []
        for geom in building.iter(f"{{*}}{surf_type}Surface"):
          dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
          for poly in geom.iter("{*}Polygon"):
            wkt = gmlPolygon2wkt(poly, dim, swap_axes=args.swap_axes)
            if wkt:
              polygons[surf_type].append(wkt)
        if polygons[surf_type]:
          multipoly_wkt = f"MULTIPOLYGON({','.join(polygons[surf_type])})"
          polygons_wkt[surf_type] = f"SRID={args.srid}; {multipoly_wkt}"
        else:
          polygons_wkt[surf_type] = f"SRID={args.srid}; MULTIPOLYGONZ EMPTY"

      # Compute footprint
      polys = []
      for poly in polygons["Ground"]:
        poly = shp.from_wkt(f"POLYGON{poly}")
        poly = shp.force_2d(poly)
        if shp.is_valid(poly):
          polys.append(poly)
      if polys:
        footprint = None
        try:
          footprint = shp.unary_union(polys)
        except shp.errors.GEOSException as e:
          print(
            "Weird edge case in Saxony caught by dividing unary union in 3 steps..."
          )
          a = shp.unary_union(polys[:5])
          b = shp.unary_union(polys[5:])
          footprint = shp.unary_union([a, b])
        if isinstance(footprint, shp.Polygon):
          footprint = shp.MultiPolygon([footprint])
        footprint_str = f"SRID={args.srid}; {shp.to_wkt(footprint)}"
      else:
        footprint_str = f"SRID={args.srid}; MULTIPOLYGON EMPTY"

      tuples.append(
        {
          "id": building_id,
          "filename": filename.name,
          "roof": polygons_wkt["Roof"],
          "wall": polygons_wkt["Wall"],
          "ground": polygons_wkt["Ground"],
          "footprint": footprint_str,
          "bl": args.bundesland,
        }
      )
      if len(tuples) >= 1024:
        insert_tuples(cur, tuples, conf)
        n_buildings += len(tuples)
        tuples = []

    insert_tuples(cur, tuples, conf)
    n_buildings += len(tuples)

    cur.execute(
      "INSERT INTO imports (filename, md5sum, count, bundesland) values (%s, %s, %s, %s)",
      (
        filename.name,
        md5sum(filename),
        n_buildings,
        args.bundesland,
      ),
    )
  return n_buildings


def main():
  with open("config.yaml", "r") as f:
    config = munchify(yaml.safe_load(f))

  parser = argparse.ArgumentParser("citygml2pgsql")
  parser.add_argument("base_path", type=Path)
  parser.add_argument("srid", type=int)
  parser.add_argument(
    "lod", type=str, choices=["lod1", "lod2", "lod3", "lod4"], default="lod2"
  )
  parser.add_argument(
    "--swap-axes", dest="swap_axes", action=argparse.BooleanOptionalAction
  )
  parser.add_argument("-j", "--threads", dest="threads", type=int, default=24)
  parser.add_argument("--bundesland", type=str, default="")
  args = parser.parse_args()

  print()
  print(f"==== Starting import for {args.base_path} ====")

  all_files = list(args.base_path.glob("**/*.gml"))
  if not all_files:
    all_files = list(args.base_path.glob("**/*.xml"))

  conn = psycopg2.connect(
    database=config.db.database, host=config.db.host, port=config.db.port
  )
  cur = conn.cursor()
  cur.execute("select filename from imports;")
  already_read = set(i for (i,) in cur)
  conn.close()

  files = [f for f in all_files if f.name not in already_read]
  if not files:
    print("Nothing to do -- all files imported already!")
    return

  print(
    f"Importing {len(files)} files (Skipping {len(all_files) - len(files)} files that were already imported)"
  )

  def process_file(filename):
    count = citygml2pgsql(filename, config, args)
    return filename, count

  total = 0
  progress = tqdm(pl.map(process_file, files, workers=args.threads), total=len(files))
  # progress = tqdm(map(process_file, files), total=len(files))
  for filename, count in progress:
    total += count
    progress.set_description(f"Processing {filename.name} Total bldgs: {total}")


if __name__ == "__main__":
  main()
