CREATE TABLE public.buildings (
    id text NOT NULL PRIMARY KEY,
    filename TEXT,
    -- lod2 GEOMETRY(MultiPolygonZ, 3857),
    roof GEOMETRY(MultiPolygonZ, 3857),
    wall GEOMETRY(MultiPolygonZ, 3857),
    ground GEOMETRY(MultiPolygonZ, 3857),
    footprint GEOMETRY(MultiPolygon,3857),
    bl CHARACTER(2)
);

-- CREATE TABLE public.footprints (  
--   id        TEXT NOT NULL PRIMARY KEY,
--   footprint GEOMETRY(MultiPolygon,3857),
--   bl        CHARACTER(2)
-- );

CREATE TABLE public.imports (
    filename TEXT,
    md5sum CHARACTER(32),
    count INTEGER,
    bundesland TEXT
);
