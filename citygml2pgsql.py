#!/usr/bin/python
# coding: utf-8

import re
from lxml import etree
import yaml
import psycopg2
from psycopg2.extras import execute_batch
import argparse
from pathlib import Path
from tqdm import tqdm
import pypeln.process as pl
from munch import munchify
from subprocess import check_output


def gmlLinearRing2wkt(ring, dim, swap_axes):
  dim = int(ring.get("srsDimension")) if ring.get("srsDimension") else dim
  dim = int(ring[0].get("srsDimension")) if ring[0].get("srsDimension") else dim
  dim = dim if dim else 3
  raw_coord = ring[0].text.split()
  coord = [raw_coord[i : i + dim] for i in range(0, len(raw_coord), dim)]
  if swap_axes:
    for i in range(len(coord)):
      coord[i] = [coord[i][1], coord[i][0], *coord[i][2:]]

  if coord[0] != coord[-1]:
    coord.append(coord[0])  # close ring if not closed
  if len(coord) < 4:
    print(
      'degenerated LinearRing gml:id="' + ring.get("{http://www.opengis.net/gml}id")
    )
    return None
  assert len(coord) >= 4
  return "(" + ",".join([" ".join(c) for c in coord]) + ")"


def gmlPolygon2wkt(poly, dim, swap_axes=False):
  dim = int(poly.get("srsDimension")) if poly.get("srsDimension") else dim
  rings = [
    _f
    for _f in [
      gmlLinearRing2wkt(ring, dim, swap_axes) for ring in poly.iter("{*}LinearRing")
    ]
    if _f
  ]
  if not rings:
    print('degenerated Polygon gml:id="' + poly.get("{http://www.opengis.net/gml}id"))
    return None
  return f"({','.join(rings)})"


def md5sum(path):
  return check_output(["md5sum", path]).decode().split(" ")[0]


def get_attrib_no_matter_the_namespace(node, attrib):
  if attrib in node.attrib:
    return node.attrib[attrib]
  for name, value in node.attrib.items():
    if name.endswith("}" + attrib):
      return value


def citygml2pgsql(filename, conf, args):
  try:
    root = etree.parse(filename)
  except etree.XMLSyntaxError as e:
    print(f"XML Error in {filename}!")
    print(e)
    return 0

  # generate a multipolygon surface per building
  geometry_types = [
    "{*}" + args.lod + geom_type
    for geom_type in ["Solid", "MultiSurface", "CompositeSurface"]
  ]
  # special treatment for Mecklenburg-Vorpommern... :)
  geometry_types += ["{*}BuildingGeometry3DLoD" + args.lod[-1]]
  tuples = []
  for building in root.iter("{*}Building"):
    building_id = get_attrib_no_matter_the_namespace(building, "id")
    building_polys = []
    for geom_type in geometry_types:
      for geom in building.iter(geom_type):
        dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
        polys = [
          _f
          for _f in [
            gmlPolygon2wkt(poly, dim, swap_axes=args.swap_axes)
            for poly in geom.iter("{*}Polygon")
          ]
          if _f
        ]
        building_polys = building_polys + polys
    if len(building_polys) == 0:
      # Panic/Saxony mode, collect all <bldg:WallSurface> and <bldg:RoofSurface> nodes as a last resort...
      for geom_type in ["bldg:WallSurface", "bldg:RoofSurface"]:
        for geom in building.iter(geom_type):
          dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
          polys = [
            _f
            for _f in [
              gmlPolygon2wkt(poly, dim, swap_axes=args.swap_axes)
              for poly in geom.iter("{*}Polygon")
            ]
            if _f
          ]
          building_polys = building_polys + polys

    if len(building_polys) != 0:
      geom_str = f"SRID={args.srid}; MULTIPOLYGON({','.join(building_polys)})"
      tuples.append({"id": building_id, "filename": filename.name, "geom": geom_str})
  conn = psycopg2.connect(
    database=conf.db.database, host=conf.db.host, port=conf.db.port
  )
  cur = conn.cursor()

  execute_batch(
    cur,
    f"INSERT INTO {conf.db.table} ({conf.columns.id}, {conf.columns.filename}, {conf.columns.geometry}) "
    f"VALUES (%(id)s, %(filename)s, ST_Transform(%(geom)s, {conf.target_srs})) "
    f"ON CONFLICT ({conf.columns.id}) DO UPDATE SET "
    f"{conf.columns.geometry}=EXCLUDED.{conf.columns.geometry}, {conf.columns.filename}=EXCLUDED.{conf.columns.filename}",
    tuples,
  )

  cur.execute(
    "INSERT INTO imports (filename, md5sum, count) values (%s, %s, %s)",
    (filename.name, md5sum(filename), len(tuples)),
  )

  conn.commit()
  return len(tuples)


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
    print(f"Nothing to do -- all files imported already!")
    return

  print(
    f"Importing {len(files)} files (Skipping {len(all_files) - len(files)} files that were already imported)"
  )

  def process_file(filename):
    count = citygml2pgsql(filename, config, args)
    return filename, count

  total = 0
  progress = tqdm(pl.map(process_file, files, workers=8), total=len(files))
  for filename, count in progress:
    total += count
    progress.set_description(f"Processing {filename.name} Total bldgs: {total}")


if __name__ == "__main__":
  main()
