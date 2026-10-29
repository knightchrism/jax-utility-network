"""SYNTHETIC gravity sewer on REAL streets, with ground elevations from the real USGS 3DEP DEM.

Manholes sit at street intersections and every ~350 ft. Flow direction comes from a
multi-source shortest-path tree toward 3 synthetic lift stations placed at local low
points, with uphill travel penalised. Inverts are set leaf-to-outlet with 6 ft
minimum cover and the 10 States minimum slope for 8" pipe (0.40%).
Planted defects are flagged qc_injected=1.
"""
import numpy as np
import geopandas as gpd
import networkx as nx
import rasterio
from shapely.geometry import Point, LineString
from shapely.ops import substring
from .config import RAW, CRS_FT

M2FT = 3.28084
MH_SPACING = 350.0
MIN_COVER = 6.0
MIN_SLOPE = {8: 0.0040, 10: 0.0028, 12: 0.0022, 15: 0.0015}


def K(c):
    return (round(c[0], 1), round(c[1], 1))


def ground(points_ft):
    with rasterio.open(RAW / "dem_3dep_aoi.tif") as r:
        ll = gpd.GeoSeries(points_ft, crs=CRS_FT).to_crs(4326)
        z = np.array([v[0] for v in r.sample([(p.x, p.y) for p in ll])], dtype=float)
    return np.clip(z, 0, None) * M2FT


def build_sewer(streets, parcels, rng):
    # 1. subdivide streets -> pipe reaches between manholes
    reaches = []
    for g in streets.geometry:
        n = max(1, int(np.ceil(g.length / MH_SPACING)))
        reaches += [substring(g, g.length * i / n, g.length * (i + 1) / n) for i in range(n)]
    G = nx.Graph()
    for g in reaches:
        G.add_edge(K(g.coords[0]), K(g.coords[-1]), geom=g)
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    nodes = list(G.nodes)
    z = dict(zip(nodes, ground([Point(n) for n in nodes])))
    # 2. lift stations: lowest node in each of 3 longitude bands
    xs = np.array([n[0] for n in nodes])
    edges = np.quantile(xs, [0, 1 / 3, 2 / 3, 1])
    lifts = []
    for a, b in zip(edges[:-1], edges[1:]):
        band = [n for n in nodes if a <= n[0] <= b]
        lifts.append(min(band, key=lambda n: z[n]))
    # 3. flow tree: Dijkstra from lift stations; uphill (toward outlet) is penalised
    for u, v, d in G.edges(data=True):
        d["w"] = d["geom"].length * (1 + 4 * abs(z[u] - z[v]) / max(d["geom"].length, 1) * 100)
    dist, paths = nx.multi_source_dijkstra(G, set(lifts), weight="w")
    down = {}  # node -> downstream node
    for n, p in paths.items():
        if len(p) > 1:
            down[n] = p[-2]
    outlet = {n: p[0] for n, p in paths.items()}
    T = nx.DiGraph([(n, d) for n, d in down.items()])
    # 4. inverts: process in reverse topological order (outlets last)
    inv = {}
    order = list(nx.topological_sort(T))
    diam = {}
    for n in order:
        ups = list(T.predecessors(n))
        cand = z[n] - MIN_COVER
        for u in ups:
            L = G.edges[u, n]["geom"].length
            n_up = len(nx.ancestors(T, u)) + 1
            d = 8 if n_up < 40 else 10 if n_up < 120 else 12 if n_up < 300 else 15
            diam[(u, n)] = d
            cand = min(cand, inv[u] - MIN_SLOPE[d] * L)
        inv[n] = cand
    mains, mh = [], []
    mid = {n: f"MH{i+1:05d}" for i, n in enumerate(order)}
    for u, n in T.edges:
        g = G.edges[u, n]["geom"]
        if K(g.coords[0]) != u:
            g = LineString(g.coords[::-1])
        L = g.length
        mains.append(dict(main_id=f"SM{len(mains)+1:05d}", us_mh=mid[u], ds_mh=mid[n], diameter_in=diam[(u, n)],
                          us_invert_ft=round(inv[u], 2), ds_invert_ft=round(inv[n], 2), length_ft=round(L, 1),
                          slope_pct=round(100 * (inv[u] - inv[n]) / L, 3), lift_station=f"LS-{lifts.index(outlet[n])+1}",
                          material="PVC" if rng.random() < .6 else "VCP", qc_injected=0, geometry=g))
    for n in order:
        mh.append(dict(mh_id=mid[n], rim_ft=round(z[n], 2), invert_ft=round(inv[n], 2), depth_ft=round(z[n] - inv[n], 2),
                       lift_station=f"LS-{lifts.index(outlet[n])+1}", is_lift_station=n in lifts, qc_injected=0, geometry=Point(n)))
    mains = gpd.GeoDataFrame(mains, crs=CRS_FT)
    mh = gpd.GeoDataFrame(mh, crs=CRS_FT)
    ls = mh[mh.is_lift_station].copy()
    ls["ls_id"] = ls.lift_station
    ls["name"] = ls.ls_id.map(lambda s: f"Synthetic Lift Station {s}")
    # 5. laterals: each real parcel -> nearest sewer main
    sidx = mains.sindex
    lat = []
    for i, p in parcels.iterrows():
        c = p.geometry.representative_point()
        j = sidx.nearest(c, return_all=False)[1][0]
        m = mains.iloc[j]
        tap = m.geometry.interpolate(m.geometry.project(c))
        lat.append(dict(lateral_id=f"SL{i+1:05d}", parcel_id=p.PARCEL_ID, main_id=m.main_id, lift_station=m.lift_station, geometry=LineString([c, tap])))
    lat = gpd.GeoDataFrame(lat, crs=CRS_FT)
    # 6. planted defects
    i = rng.choice(len(mains), 5, replace=False)  # adverse slope: raise the downstream invert
    for k in i:
        mains.loc[k, "ds_invert_ft"] = mains.loc[k, "us_invert_ft"] + 0.4
        mains.loc[k, "slope_pct"] = round(-100 * 0.4 / mains.loc[k, "length_ft"], 3)
        mains.loc[k, "qc_injected"] = 1
    # flow loop: reverse one main so its downstream manhole drains back to its upstream manhole
    k = int(mains[(mains.qc_injected == 0)].sample(1, random_state=7).index[0])
    r = mains.loc[k].copy()
    loop = r.copy(); loop["main_id"] = "SM99001"; loop["us_mh"], loop["ds_mh"] = r.ds_mh, r.us_mh
    loop["geometry"] = LineString(list(r.geometry.coords)[::-1]).parallel_offset(3) if False else LineString(list(r.geometry.coords)[::-1])
    loop["qc_injected"] = 1
    mains = gpd.GeoDataFrame(list(mains.to_dict("records")) + [loop.to_dict()], crs=CRS_FT)
    b = mains.total_bounds
    orph = [dict(mh_id=f"MH9900{k}", rim_ft=10.0, invert_ft=3.0, depth_ft=7.0, lift_station=None, is_lift_station=False, qc_injected=1,
                 geometry=Point(b[0] + 500 + 700 * k, b[3] - 200)) for k in range(3)]
    mh = gpd.GeoDataFrame(list(mh.to_dict("records")) + orph, crs=CRS_FT)
    return mains, mh, ls[["ls_id", "name", "rim_ft", "invert_ft", "geometry"]], lat
