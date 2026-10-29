"""Build SYNTHETIC water + electric distribution networks on REAL streets/parcels.

Everything written by this module is SYNTHETIC (prefix `synthetic_`), except
re-projected copies of real inputs (prefix `real_`). Deliberate QC defects are
injected (flagged `qc_injected=1`) so the topology QC has something to find.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union, substring
from .config import RAW, SYN, PROC, AOI, CRS_FT

rng = np.random.default_rng(904)  # 904 = JAX area code, deterministic
VALVE_OFFSET = 20.0  # ft from intersection


def load_real():
    clip = gpd.GeoSeries([box(*AOI)], crs=4326).to_crs(CRS_FT).iloc[0]
    roads = pd.concat([gpd.read_file(RAW / f) for f in ["roads_aoi.geojson", "roads_secondary_aoi.geojson"]])
    roads = roads.to_crs(CRS_FT).clip(clip).explode(index_parts=False)
    roads = roads[roads.geom_type == "LineString"]
    parcels = gpd.read_file(RAW / "parcels_aoi.geojson").to_crs(CRS_FT)
    parcels = parcels[parcels.representative_point().within(clip)].drop_duplicates("PARCEL_ID").reset_index(drop=True)
    hyd = gpd.read_file(RAW / "hydrants_aoi.geojson").to_crs(CRS_FT)
    hyd = hyd[hyd.within(clip)].reset_index(drop=True)
    tx = gpd.read_file(RAW / "hifld_transmission_duval.geojson").to_crs(CRS_FT)
    return clip, roads, parcels, hyd, tx


def node_streets(roads):
    """Split real centerlines at every intersection -> clean edge list."""
    merged = unary_union(roads.geometry.values)
    segs = [g for g in getattr(merged, "geoms", [merged]) if g.length > 1]
    return gpd.GeoDataFrame(geometry=segs, crs=CRS_FT)


def key(pt):
    return (round(pt[0], 1), round(pt[1], 1))


def build_water(streets, parcels, hyd):
    deg = {}
    for g in streets.geometry:
        for c in (g.coords[0], g.coords[-1]):
            deg[key(c)] = deg.get(key(c), 0) + 1
    mains, valves = [], []
    G = nx.Graph()
    mid = 0
    for g in streets.geometry:
        ends = [key(g.coords[0]), key(g.coords[-1])]
        cuts = [0.0]
        if deg[ends[0]] >= 3 and g.length > 3 * VALVE_OFFSET:
            cuts.append(VALVE_OFFSET)
        if deg[ends[1]] >= 3 and g.length > 3 * VALVE_OFFSET:
            cuts.append(g.length - VALVE_OFFSET)
        cuts.append(g.length)
        pieces = [substring(g, a, b) for a, b in zip(cuts[:-1], cuts[1:])]
        diam = 12 if g.length > 1500 else int(rng.choice([6, 8, 8, 8]))
        for i, pc in enumerate(pieces):
            mid += 1
            mains.append(dict(main_id=f"WM{mid:05d}", diameter_in=diam, material=str(rng.choice(["DIP", "PVC", "CI"], p=[.5, .35, .15])),
                              install_year=int(rng.integers(1925, 2020)), qc_injected=0, geometry=pc))
            u, v = key(pc.coords[0]), key(pc.coords[-1])
            G.add_edge(u, v, main_id=f"WM{mid:05d}")
            if i > 0:  # node between pieces is a valve
                valves.append(dict(valve_id=f"WV{len(valves)+1:05d}", status="OPEN", qc_injected=0, geometry=Point(u)))
                G.nodes[u]["valve"] = valves[-1]["valve_id"]
    mains = gpd.GeoDataFrame(mains, crs=CRS_FT)
    valves = gpd.GeoDataFrame(valves, crs=CRS_FT)

    # services + meters: one per REAL parcel, to nearest main
    sidx = mains.sindex
    svc, met = [], []
    for i, p in parcels.iterrows():
        c = p.geometry.representative_point()
        j = sidx.nearest(c, return_all=False)[1][0]
        m = mains.iloc[j]
        tap = m.geometry.interpolate(m.geometry.project(c))
        line = LineString([tap, c])
        meter = line.interpolate(0.25, normalized=True)  # near the street / property line
        svc.append(dict(service_id=f"WS{i+1:05d}", parcel_id=p.PARCEL_ID, main_id=m.main_id, size_in=1.0 if p.DOR_UC in ("001", "000") else 2.0, geometry=line))
        met.append(dict(meter_id=f"MTR{i+1:05d}", parcel_id=p.PARCEL_ID, service_id=f"WS{i+1:05d}", main_id=m.main_id, geometry=meter))
    svc = gpd.GeoDataFrame(svc, crs=CRS_FT)
    met = gpd.GeoDataFrame(met, crs=CRS_FT)

    # REAL hydrants snapped to synthetic main via synthetic lateral
    lat = []
    for _, h in hyd.iterrows():
        j = sidx.nearest(h.geometry, return_all=False)[1][0]
        m = mains.iloc[j]
        tap = m.geometry.interpolate(m.geometry.project(h.geometry))
        lat.append(dict(hydrant_id=int(h.Hydrant_ID), main_id=m.main_id, length_ft=round(tap.distance(h.geometry), 1), geometry=LineString([tap, h.geometry])))
    lat = gpd.GeoDataFrame(lat, crs=CRS_FT)

    # --- inject QC defects (documented) ---
    mains.loc[rng.choice(len(mains), 6, replace=False), ["diameter_in", "qc_injected"]] = [np.nan, 1]
    dup = mains.sample(2, random_state=1).copy(); dup["main_id"] = [f"WM9{k:04d}" for k in range(2)]; dup["qc_injected"] = 1
    b = mains.total_bounds
    orphan = [dict(main_id=f"WM8{k:04d}", diameter_in=8, material="PVC", install_year=2021, qc_injected=1,
                   geometry=LineString([(b[0] + 300 + k * 900, b[1] + 250), (b[0] + 300 + k * 900, b[1] + 520)])) for k in range(2)]
    mains = pd.concat([mains, dup, gpd.GeoDataFrame(orphan, crs=CRS_FT)], ignore_index=True)
    off = valves.sample(3, random_state=2).copy()
    off["geometry"] = off.geometry.translate(35, 35); off["valve_id"] = [f"WV9{k:04d}" for k in range(3)]; off["qc_injected"] = 1
    valves = pd.concat([valves, off], ignore_index=True)
    return mains, valves, svc, met, lat


def build_electric(streets, parcels, tx, clip):
    # synthetic substation at SW corner of AOI, tied to nearest REAL HIFLD line
    G = nx.Graph()
    for g in streets.geometry:
        G.add_edge(key(g.coords[0]), key(g.coords[-1]), geom=g, length=g.length)
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    corner = Point(clip.bounds[0], clip.bounds[1])
    src = min(G.nodes, key=lambda n: Point(n).distance(corner))
    near_tx = tx.iloc[tx.distance(Point(src)).argmin()]
    sub = dict(sub_id="SUB-SYN-01", name="Synthetic Riverside Sub", kv_high=near_tx.VOLTAGE, kv_low=13.2, tie_hifld_id=str(near_tx.ID),
               geometry=Point(src).buffer(1).centroid)
    T = nx.minimum_spanning_tree(G, weight="length")  # radial
    D = nx.bfs_tree(T, src)
    # 3 feeders: cut the radial tree into ~equal subtrees (greedy, by node count)
    fids = ["FDR-101", "FDR-102", "FDR-103"]
    feeder_of = {n: fids[0] for n in D.nodes}
    Dw = D.copy()
    N = Dw.number_of_nodes()
    for fid in fids[1:]:
        size = {n: len(nx.descendants(Dw, n)) + 1 for n in Dw.nodes if n != src}
        cut = min(size, key=lambda n: abs(size[n] - N / 3))
        sub_nodes = nx.descendants(Dw, cut) | {cut}
        for n in sub_nodes:
            feeder_of[n] = fid
        Dw.remove_nodes_from(sub_nodes)
    prim, fuses = [], []
    depth = nx.shortest_path_length(D, src)
    for u, v in D.edges:
        g = T.edges[u, v]["geom"]
        fd = feeder_of.get(v, "FDR-101")
        n_down = len(nx.descendants(D, v))
        trunk = n_down >= 8 or u == src
        prim.append(dict(seg_id=f"PRI{len(prim)+1:05d}", feeder_id=fd, from_node=str(u), to_node=str(v),
                         phase="ABC" if trunk else str(rng.choice(["A", "B", "C"])), voltage_kv=13.2,
                         kind="trunk" if trunk else "lateral", qc_injected=0, geometry=g))
        if not trunk and feeder_of.get(u) and len(nx.descendants(D, u)) >= 8:  # lateral tap off trunk
            p = g.interpolate(min(15, g.length / 2)) if Point(g.coords[0]).distance(Point(u)) < 1 else g.interpolate(g.length - min(15, g.length / 2))
            fuses.append(dict(fuse_id=f"FU{len(fuses)+1:04d}", feeder_id=fd, protects_node=str(v), amps=int(rng.choice([40, 65, 100])), geometry=p))
    prim = gpd.GeoDataFrame(prim, crs=CRS_FT)
    fuses = gpd.GeoDataFrame(fuses, crs=CRS_FT)
    # transformers: group parcels by nearest primary segment, ~6 customers each
    sidx = prim.sindex
    parcels = parcels.copy()
    cents = parcels.geometry.representative_point()
    parcels["seg"] = [sidx.nearest(c, return_all=False)[1][0] for c in cents]
    xf, drops = [], []
    for seg, grp in parcels.groupby("seg"):
        s = prim.iloc[seg]
        grp = grp.assign(pos=[s.geometry.project(c) for c in cents[grp.index]]).sort_values("pos")
        k = max(1, int(np.ceil(len(grp) / 6)))
        for ci in np.array_split(np.arange(len(grp)), k):
            chunk = grp.iloc[ci]
            if chunk.empty: continue
            loc = s.geometry.interpolate(chunk.pos.mean())
            tid = f"XF{len(xf)+1:05d}"
            xf.append(dict(xfmr_id=tid, seg_id=s.seg_id, feeder_id=s.feeder_id, node=s.to_node, phase=s.phase[0], kva=int(rng.choice([25, 37.5, 50])) if len(chunk) <= 6 else 75,
                           voltage_kv=13.2, n_customers=len(chunk), qc_injected=0, geometry=loc))
            for _, p in chunk.iterrows():
                drops.append(dict(drop_id=f"SD{len(drops)+1:05d}", parcel_id=p.PARCEL_ID, xfmr_id=tid, feeder_id=s.feeder_id,
                                  geometry=LineString([loc, cents[p.name]])))
    xf = gpd.GeoDataFrame(xf, crs=CRS_FT)
    drops = gpd.GeoDataFrame(drops, crs=CRS_FT)
    # inject defects
    i = rng.choice(len(xf), 4, replace=False)
    xf.loc[i[:2], ["phase", "qc_injected"]] = [None, 1]
    xf.loc[i[2:], ["voltage_kv", "qc_injected"]] = [np.nan, 1]
    b = prim.total_bounds
    orphan = xf.iloc[:2].copy(); orphan["xfmr_id"] = ["XF9001", "XF9002"]; orphan["seg_id"] = None; orphan["qc_injected"] = 1
    orphan["geometry"] = [Point(b[2] - 120, b[3] - 140), Point(b[2] - 400, b[3] - 90)]; orphan["n_customers"] = 0
    xf = pd.concat([xf, orphan], ignore_index=True)
    prim.loc[rng.choice(len(prim), 3, replace=False), ["phase", "qc_injected"]] = [None, 1]
    return gpd.GeoDataFrame([sub], crs=CRS_FT), prim, fuses, xf, drops


def main():
    SYN.mkdir(exist_ok=True, parents=True); PROC.mkdir(exist_ok=True, parents=True)
    clip, roads, parcels, hyd, tx = load_real()
    streets = node_streets(roads)
    mains, valves, svc, met, lat = build_water(streets, parcels, hyd)
    sub, prim, fuses, xf, drops = build_electric(streets, parcels, tx, clip)
    from .sewer import build_sewer
    smains, smh, sls, slat = build_sewer(streets, parcels, rng)
    septic = gpd.read_file(RAW / "septic_phaseout_areas.geojson").to_crs(CRS_FT)
    osm = gpd.read_file(RAW / "osm_power_duval.geojson").to_crs(CRS_FT)
    layers = {
        "real_streets_tiger": streets, "real_parcels_fdor": parcels[["PARCEL_ID", "DOR_UC", "PHY_ADDR1", "geometry"]],
        "real_hydrants_jea": hyd, "real_transmission_hifld": tx,
        "synthetic_water_mains": mains, "synthetic_water_valves": valves, "synthetic_water_services": svc,
        "synthetic_water_meters": met, "synthetic_hydrant_laterals": lat,
        "synthetic_substation": sub, "synthetic_primary_conductor": prim, "synthetic_fuses": fuses,
        "synthetic_transformers": xf, "synthetic_service_drops": drops,
        "synthetic_sewer_mains": smains, "synthetic_sewer_manholes": smh, "synthetic_lift_stations": sls, "synthetic_sewer_laterals": slat,
        "real_septic_phaseout_coj": septic,
        "real_osm_power_lines": osm[osm.power.isin(["line", "minor_line", "cable"])],
        "real_osm_power_substations": osm[osm.power == "substation"],
        "real_osm_power_poles_towers": osm[osm.power.isin(["pole", "tower", "transformer"])],
    }
    gpkg = PROC / "jax_utility_network.gpkg"
    gpkg.unlink(missing_ok=True)
    for name, g in layers.items():
        g.to_file(gpkg, layer=name, driver="GPKG")
        if name.startswith("synthetic_"):
            g.to_crs(4326).to_file(SYN / f"{name}.geojson", driver="GeoJSON")
        print(f"{name:32s} {len(g):6d}")


if __name__ == "__main__":
    main()
