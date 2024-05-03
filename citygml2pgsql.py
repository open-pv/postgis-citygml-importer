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


def gmlLinearRing2wkt(ring, dim):
    dim = int(ring.get("srsDimension")) if ring.get("srsDimension") else dim
    dim = int(ring[0].get("srsDimension")) if ring[0].get("srsDimension") else dim
    dim = dim if dim else 3
    raw_coord = ring[0].text.split()
    coord = [raw_coord[i:i+dim] for i in range(0, len(raw_coord), dim)]
    if coord[0] != coord[-1]:
        coord.append(coord[0]) # close ring if not closed
    if len(coord) < 4:
        print( 'degenerated LinearRing gml:id="'+\
                ring.get("{http://www.opengis.net/gml}id")+'"\n')
        return None
    assert len(coord) >= 4
    return f"("+",".join([" ".join(c) for c in coord])+")"

def gmlPolygon2wkt(poly, dim):
    dim = int(poly.get("srsDimension")) if poly.get("srsDimension") else dim
    rings = [_f for _f in [gmlLinearRing2wkt(ring, dim) \
            for ring in poly.iter("{http://www.opengis.net/gml}LinearRing") ] if _f]
    if not rings:
        print( 'degenerated Polygon gml:id="'+\
                poly.get("{http://www.opengis.net/gml}id")+'"\n')
        return None
    return f"({','.join(rings)})"

def findNamespaceFor(elmentName, root):
    for e in root.iter():
        if e.tag is etree.Comment:
            continue
        m = re.match(r"(.*)"+elmentName, e.tag) if e.tag else None
        if m:
            return m.groups()[0]
    return None

def fullName(elmentName, root):
    namespace = findNamespaceFor(elmentName, root)
    return namespace+elmentName if namespace else None

def buildingGeomTypes(root, lods=[0, 1, 2, 3]):
    types = set()
    name = fullName('Building', root)
    if not name:
        return types
    for building in root.iter(name):
        for geom_type in ['Solid', 'MultiSurface', 'CompositeSurface']:
            for lod in lods :
                type_ = fullName('lod'+str(lod)+geom_type, building)
                if type_:
                   types.add(type_)
    return types


def citygml2pgsql(filename, conf, args):
    if not filename.exists():
      raise RuntimeError("error: cannot find "+filename)

    root = etree.parse(filename)
    #generate a multipolygon surface per building
    geom_types = buildingGeomTypes(root, [int(args.lod[-1])])
    num_inserts = 0

    tuples = []
    for building in root.iter(fullName("Building", root)):
      try:
        building_id = building.attrib["{http://www.opengis.net/gml}id"]
      except KeyError:
        pass
      building_polys = []
      for geom_type in geom_types:
          for geom in building.iter(geom_type):
              dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
              polys = [_f for _f in [gmlPolygon2wkt(poly, dim) \
                            for poly in geom.iter(fullName("Polygon", building))] if _f]
              building_polys = building_polys + polys
      if len(building_polys) == 0:
        # Panic/Saxony mode, collect all <bldg:WallSurface> and <bldg:RoofSurface> nodes as a last resort...
        for geom_type in ['bldg:WallSurface', 'bldg:RoofSurface']:
          for geom in building.iter(geom_type):
              dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
              polys = [_f for _f in [gmlPolygon2wkt(poly, dim) \
                            for poly in geom.iter(fullName("Polygon", building))] if _f]
              building_polys = building_polys + polys

      if len(building_polys) != 0:
        geom_str = f"SRID={args.srid}; MULTIPOLYGON({','.join(building_polys)})"
        tuples.append({
          'id': building_id,
          'filename': filename.name,
          'geom': geom_str
        })
    # conn = psycopg2.connect(database=conf.db.database, host=conf.db.host, port=conf.db.port)
    # cur = conn.cursor()

    # execute_batch(cur,
    #   f'INSERT INTO {config.db.table} ({config.columns.id}, {config.columns.filename}, {config.columns.geometry}) '
    #   f'VALUES (%(id)s, %(filename)s, ST_Transform(%(geom)s, {config.target_srs})) '
    #   f'ON CONFLICT ({config.columns.id}) DO UPDATE SET '
    #   f'{config.columns.geometry}=EXCLUDED.{config.columns.geometry}, {config.columns.filename}=EXCLUDED.{config.columns.filename}',
    #   tuples
    # )

    # conn.commit()
    return len(tuples)


if __name__ == '__main__':
  with open('config.yaml', 'r') as f:
    config = munchify(yaml.safe_load(f))

  parser = argparse.ArgumentParser('citygml2pgsql')
  parser.add_argument('base_path', type=Path)
  parser.add_argument('srid', type=int)
  parser.add_argument('lod', type=str, choices=['lod1', 'lod2', 'lod3', 'lod4'], default='lod2')
  args = parser.parse_args()

  print(f'Starting import for {args.base_path}')

  all_files = list(args.base_path.glob('**/*.gml'))
  if not all_files:
    all_files = list(args.base_path.glob('**/*.xml'))
  print(f'Found {len(all_files)} files')

  # conn = psycopg2.connect(database=config.db.database, host=config.db.host, port=config.db.port)
  # cur = conn.cursor()
  # cur.execute('select distinct filename from buildings;')
  # already_read = set(i for i, in cur)
  # conn.close()

  already_read = set()
  files = [f for f in all_files if f.name not in already_read]
  print(f'Skipping {len(all_files) - len(files)} files that were already processed')

  def process_file(filename):
    count = citygml2pgsql(filename, config, args)
    return filename, count

  total = 0
  # progress = tqdm(pl.map(process_file, files, workers=8), total=len(files))
  files = files[:10]
  progress = tqdm(map(process_file, files), total=len(files))
  for (filename, count) in progress:
    total += count
    progress.set_description(f'Processing {filename.name} Total bldgs: {total}')

