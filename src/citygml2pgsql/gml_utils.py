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
