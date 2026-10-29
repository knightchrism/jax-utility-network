"""REAL OSM power data (lines, substations, poles, towers, transformers) from a Geofabrik
Florida extract, clipped to Duval County. Data (c) OpenStreetMap contributors, ODbL."""
import sys
import requests
import osmium
import geopandas as gpd
from shapely import wkb
from .config import RAW, PROC, GEOFABRIK_FL, CRS_FT

PBF = RAW / "florida-latest.osm.pbf"


class Power(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.f = osmium.geom.WKBFactory()
        self.rows = []

    def _add(self, o, geom):
        t = o.tags
        self.rows.append(dict(osm_id=o.id, power=t.get("power"), voltage=t.get("voltage"), operator=t.get("operator"),
                              name=t.get("name"), substation=t.get("substation"), geometry=wkb.loads(geom, hex=True)))

    def node(self, n):
        if n.tags.get("power") in ("pole", "tower", "transformer", "substation"):
            self._add(n, self.f.create_point(n))

    def way(self, w):
        p = w.tags.get("power")
        if p in ("line", "minor_line", "cable"):
            try: self._add(w, self.f.create_linestring(w))
            except Exception: pass

    def area(self, a):
        if a.tags.get("power") == "substation":
            try: self._add(a, self.f.create_multipolygon(a))
            except Exception: pass


def main():
    if not PBF.exists():
        with requests.get(GEOFABRIK_FL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(PBF, "wb") as fh:
                for ch in r.iter_content(1 << 20): fh.write(ch)
    county = gpd.read_file("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query?where=GEOID%3D%2712031%27&outFields=NAME&outSR=4326&f=geojson")
    b = county.total_bounds
    h = Power()
    h.apply_file(str(PBF), locations=True, idx="flex_mem")
    g = gpd.GeoDataFrame(h.rows, crs=4326)
    g = g.cx[b[0]:b[2], b[1]:b[3]]
    g = gpd.clip(g, county.geometry.iloc[0])
    county.to_file(RAW / "duval_county_tiger.geojson", driver="GeoJSON")
    g.to_file(RAW / "osm_power_duval.geojson", driver="GeoJSON")
    print(g.groupby([g.power, g.geom_type]).size())


if __name__ == "__main__":
    sys.exit(main())
