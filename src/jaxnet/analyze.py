"""Topology QC + valve-isolation trace + fuse outage trace + hydrant coverage + maps."""
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .config import RAW, PROC, OUT, WEB, CRS_FT

GPKG = PROC / "jax_utility_network.gpkg"
K = lambda c: (round(c[0], 1), round(c[1], 1))  # noqa


def L(name):
    return gpd.read_file(GPKG, layer=name)


def water_graph(mains):
    G = nx.Graph()
    for _, m in mains.iterrows():
        G.add_edge(K(m.geometry.coords[0]), K(m.geometry.coords[-1]), main_id=m.main_id)
    return G


def qc(mains, valves, svc, prim, xf, sub):
    R = {}
    G = water_graph(mains)
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    small = [c for c in comps[1:]]
    R["water_components"] = len(comps)
    R["water_disconnected_mains"] = sorted({G.edges[e]["main_id"] for c in small for e in G.subgraph(c).edges})
    dangles = [n for n in G.nodes if G.degree(n) == 1]
    short = []
    for n in dangles:
        mid = G.edges[next(iter(G.edges(n)))]["main_id"]
        if mains.loc[mains.main_id == mid].geometry.length.iloc[0] < 60:
            short.append(mid)
    R["water_dead_ends"] = len(dangles)
    R["water_short_dangles_lt60ft"] = sorted(set(short))
    R["water_missing_diameter"] = mains.loc[mains.diameter_in.isna(), "main_id"].tolist()
    wkb = mains.geometry.normalize().to_wkb()
    R["water_duplicate_geometry"] = mains.loc[wkb.duplicated(keep="first"), "main_id"].tolist()
    d = valves.geometry.apply(lambda p: mains.distance(p).min())
    R["water_valves_off_main"] = valves.loc[d > 0.5, "valve_id"].tolist()
    # electric
    E = nx.Graph()
    for _, s in prim.iterrows():
        E.add_edge(s.from_node, s.to_node)
    srcnode = prim.loc[prim.kind == "trunk"].iloc[0].from_node
    reach = nx.node_connected_component(E, srcnode)
    R["elec_primary_unreachable_from_sub"] = prim.loc[~prim.to_node.isin(reach), "seg_id"].tolist()
    dx = xf.geometry.apply(lambda p: prim.distance(p).min())
    R["elec_unconnected_transformers"] = xf.loc[(dx > 1) | xf.seg_id.isna(), "xfmr_id"].tolist()
    R["elec_xfmr_missing_phase"] = xf.loc[xf.phase.isna(), "xfmr_id"].tolist()
    R["elec_xfmr_missing_voltage"] = xf.loc[xf.voltage_kv.isna(), "xfmr_id"].tolist()
    R["elec_primary_missing_phase"] = prim.loc[prim.phase.isna(), "seg_id"].tolist()
    return R


def isolation_trace(mains, valves, svc):
    G = water_graph(mains)
    vnodes = {K(p.coords[0]) for p in valves.geometry}
    load = svc.groupby("main_id").size()
    cand = mains[(mains.qc_injected == 0) & mains.main_id.isin(load.index)].copy()
    cand["n"] = cand.main_id.map(load)
    def trace(brk):
        u, v = K(brk.geometry.coords[0]), K(brk.geometry.coords[-1])
        seen_e, close, stack, seen_n = {brk.main_id}, set(), [u, v], set()
        while stack:
            n = stack.pop()
            if n in seen_n: continue
            seen_n.add(n)
            if n in vnodes:
                close.add(n); continue
            for nb in G.neighbors(n):
                seen_e.add(G.edges[n, nb]["main_id"])
                stack.append(nb)
        return seen_e, close
    # pick a representative break: among busy mains, the one with the most affected parcels that needs >= 3 valves
    best = None
    for _, brk in cand.sort_values("n", ascending=False).head(300).iterrows():
        seen_e, close = trace(brk)
        score = (len(close) >= 3, int(svc.main_id.isin(seen_e).sum()))
        if best is None or score > best[3]:
            best = (brk, seen_e, close, score)
    best = best[:3]
    brk, seen_e, close = best
    vids = valves[valves.geometry.apply(lambda p: K(p.coords[0]) in close)].valve_id.tolist()
    aff = svc[svc.main_id.isin(seen_e)].parcel_id.unique().tolist()
    return dict(break_main=brk.main_id, isolated_mains=sorted(seen_e), valves_to_close=vids, affected_parcels=aff)


def outage_trace(prim, fuses, xf, drops):
    D = nx.DiGraph()
    for _, s in prim.iterrows():
        D.add_edge(s.from_node, s.to_node)
    best = None
    for _, f in fuses.iterrows():
        nodes = nx.descendants(D, f.protects_node) | {f.protects_node}
        t = xf[xf.node.isin(nodes)]
        n = int(t.n_customers.sum())
        if best is None or n > best[1]:
            best = (f, n, t, nodes)
    f, n, t, nodes = best
    cust = drops[drops.xfmr_id.isin(t.xfmr_id)].parcel_id.unique().tolist()
    segs = prim[prim.to_node.isin(nodes)].seg_id.tolist()
    feeder_tot = {k: int(v) for k, v in drops.groupby("feeder_id").size().items()}
    return dict(fuse=f.fuse_id, feeder=f.feeder_id, transformers=t.xfmr_id.tolist(), segments=segs,
                affected_customers=cust, feeder_customers=feeder_tot)


def coverage(parcels, hyd_buf):
    c = parcels.geometry.representative_point()
    d = c.apply(lambda p: hyd_buf.distance(p).min())
    return parcels.assign(dist_hydrant_ft=d.round(0))


def main():
    OUT.mkdir(exist_ok=True); WEB.mkdir(exist_ok=True)
    mains, valves, svc, met = L("synthetic_water_mains"), L("synthetic_water_valves"), L("synthetic_water_services"), L("synthetic_water_meters")
    prim, fuses, xf, drops, sub = L("synthetic_primary_conductor"), L("synthetic_fuses"), L("synthetic_transformers"), L("synthetic_service_drops"), L("synthetic_substation")
    parcels, hyd, streets, tx = L("real_parcels_fdor"), L("real_hydrants_jea"), L("real_streets_tiger"), L("real_transmission_hifld")
    hyd_buf = gpd.read_file(RAW / "hydrants_aoi_buffered.geojson").to_crs(CRS_FT)

    R = qc(mains, valves, svc, prim, xf, sub)
    iso = isolation_trace(mains, valves, svc)
    out = outage_trace(prim, fuses, xf, drops)
    cov = coverage(parcels, hyd_buf)
    gaps = cov[cov.dist_hydrant_ft > 500]
    summary = dict(qc={k: (len(v) if isinstance(v, list) else v) for k, v in R.items()},
                   isolation=dict(break_main=iso["break_main"], mains=len(iso["isolated_mains"]), valves=len(iso["valves_to_close"]), parcels=len(iso["affected_parcels"])),
                   outage=dict(fuse=out["fuse"], feeder=out["feeder"], transformers=len(out["transformers"]), customers=len(out["affected_customers"]), feeder_customers=out["feeder_customers"]),
                   hydrant=dict(parcels=len(cov), gt500ft=len(gaps), pct=round(100 * len(gaps) / len(cov), 1), real_hydrants_aoi=len(hyd)),
                   counts=dict(mains=len(mains), valves=len(valves), services=len(svc), meters=len(met), primary=len(prim), fuses=len(fuses), transformers=len(xf), drops=len(drops)))
    json.dump(dict(summary=summary, qc=R, isolation=iso, outage=out), open(OUT / "results.json", "w"), indent=2, default=str)

    # analysis layers to gpkg
    mains.assign(isolated=mains.main_id.isin(iso["isolated_mains"])).query("isolated").to_file(GPKG, layer="trace_valve_isolation_mains")
    cov.to_file(GPKG, layer="analysis_hydrant_coverage")
    parcels[parcels.PARCEL_ID.isin(out["affected_customers"])].to_file(GPKG, layer="trace_outage_parcels")
    parcels[parcels.PARCEL_ID.isin(iso["affected_parcels"])].to_file(GPKG, layer="trace_isolation_parcels")

    write_report(summary, R, iso, out)
    png(streets, parcels, mains, valves, hyd, prim, xf, sub, iso, out, gaps)
    leaflet(streets, parcels, mains, valves, hyd, prim, fuses, xf, sub, tx, iso, out, gaps)
    print(json.dumps(summary, indent=2))


def write_report(S, R, iso, out):
    q = S["qc"]
    rows = [
        ("Water", "Disconnected main islands (components beyond the main network)", q["water_components"] - 1, ", ".join(R["water_disconnected_mains"])),
        ("Water", "Disconnected mains (count)", q["water_disconnected_mains"], ""),
        ("Water", "Dead ends (degree-1 nodes; many are legitimate cul-de-sacs)", q["water_dead_ends"], ""),
        ("Water", "Short dangling segments < 60 ft (likely digitizing error)", q["water_short_dangles_lt60ft"], ", ".join(R["water_short_dangles_lt60ft"][:15])),
        ("Water", "Mains missing diameter", q["water_missing_diameter"], ", ".join(R["water_missing_diameter"])),
        ("Water", "Duplicate main geometry", q["water_duplicate_geometry"], ", ".join(R["water_duplicate_geometry"])),
        ("Water", "Valves not on a main (> 0.5 ft)", q["water_valves_off_main"], ", ".join(R["water_valves_off_main"])),
        ("Electric", "Primary segments unreachable from substation", q["elec_primary_unreachable_from_sub"], ""),
        ("Electric", "Unconnected transformers (> 1 ft from primary / no segment)", q["elec_unconnected_transformers"], ", ".join(R["elec_unconnected_transformers"])),
        ("Electric", "Transformers missing phase", q["elec_xfmr_missing_phase"], ", ".join(R["elec_xfmr_missing_phase"])),
        ("Electric", "Transformers missing voltage", q["elec_xfmr_missing_voltage"], ", ".join(R["elec_xfmr_missing_voltage"])),
        ("Electric", "Primary segments missing phase", q["elec_primary_missing_phase"], ", ".join(R["elec_primary_missing_phase"])),
    ]
    md = ["# GeoKnight GIS | Topology QC Report: Avondale/Riverside, Jacksonville FL", "",
          "> **SYNTHETIC NETWORK.** Water and distribution-electric assets are synthetic, generated on real Census TIGER streets and real FDOR parcels. "
          "Some defects were planted on purpose (`qc_injected=1`) to check that the QC catches them. Hydrant locations are real (City of Jacksonville / JEA service).", "",
          "| Network | Check | Count | Feature IDs (truncated) |", "|---|---|---:|---|"]
    md += [f"| {a} | {b} | {c} | {d[:160]} |" for a, b, c, d in rows]
    md += ["", "## Main-break valve isolation", f"- Break on **{iso['break_main']}**: close **{len(iso['valves_to_close'])} valves** ({', '.join(iso['valves_to_close'])})",
           f"- Isolated mains: {len(iso['isolated_mains'])}; **affected parcels: {len(iso['affected_parcels'])}**", "",
           "## Fuse outage trace", f"- Fuse **{out['fuse']}** on {out['feeder']} operates: {len(out['transformers'])} transformers, **{len(out['affected_customers'])} customers out**",
           f"- Customers per feeder (breaker-level outage): {out['feeder_customers']}", "",
           "## Hydrant coverage (real hydrants)", f"- {S['hydrant']['gt500ft']} of {S['hydrant']['parcels']} parcels ({S['hydrant']['pct']}%) are > 500 ft (straight line) from the nearest hydrant."]
    (OUT / "qc_report.md").write_text("\n".join(md) + "\n")


def png(streets, parcels, mains, valves, hyd, prim, xf, sub, iso, out, gaps):
    fig, axs = plt.subplots(1, 2, figsize=(18, 9), facecolor="#0b1220")
    for ax in axs:
        ax.set_facecolor("#0b1220"); ax.set_axis_off()
        parcels.plot(ax=ax, color="#1b2638", edgecolor="#26344d", lw=.2)
    ax = axs[0]
    mains.plot(ax=ax, color="#38bdf8", lw=.8)
    mains[mains.main_id.isin(iso["isolated_mains"])].plot(ax=ax, color="#f43f5e", lw=3)
    parcels[parcels.PARCEL_ID.isin(iso["affected_parcels"])].plot(ax=ax, color="#f43f5e", alpha=.5)
    if len(gaps): gaps.plot(ax=ax, color="#f59e0b", alpha=.6)
    hyd.plot(ax=ax, color="#fde047", markersize=6)
    valves.plot(ax=ax, color="white", markersize=2)
    ax.set_title("WATER (synthetic mains, real hydrants)\nred = valve isolation, amber = parcels >500 ft from hydrant", color="white")
    ax = axs[1]
    cols = {"FDR-101": "#a78bfa", "FDR-102": "#34d399", "FDR-103": "#fb923c"}
    for f, g in prim.groupby("feeder_id"):
        g.plot(ax=ax, color=cols.get(f, "w"), lw=1.5)
    parcels[parcels.PARCEL_ID.isin(out["affected_customers"])].plot(ax=ax, color="#f43f5e", alpha=.55)
    xf.plot(ax=ax, color="white", markersize=3)
    sub.plot(ax=ax, color="#facc15", markersize=200, marker="s")
    ax.set_title(f"ELECTRIC (synthetic distribution)\nfeeders FDR-101/102/103, red = {out['fuse']} outage", color="white")
    fig.suptitle("GeoKnight GIS  |  Jacksonville Utility Network Demo  |  Avondale / Riverside  (SYNTHETIC assets on real streets and parcels)", color="white", fontsize=15)
    plt.tight_layout(); fig.savefig(OUT / "jax_utility_network_map.png", dpi=140, facecolor=fig.get_facecolor()); plt.close(fig)


def leaflet(streets, parcels, mains, valves, hyd, prim, fuses, xf, sub, tx, iso, out, gaps):
    w = lambda g: g.to_crs(4326)  # noqa
    c = w(parcels).union_all().centroid
    m = folium.Map([c.y, c.x], zoom_start=15, tiles="OpenStreetMap", control_scale=True)
    def add(g, name, style, show=True, tip=None):
        if len(g) == 0:
            return
        fg = folium.FeatureGroup(name=name, show=show)
        g = w(g)
        g = g[[col for col in g.columns if col == "geometry" or g[col].dtype != object or True]]
        folium.GeoJson(g.to_json(default=str), style_function=lambda _: style,
                       tooltip=folium.GeoJsonTooltip(fields=tip) if tip else None,
                       marker=folium.CircleMarker(radius=style.get("radius", 3), fill=True, fill_opacity=.9) if g.geom_type.iloc[0] == "Point" else None).add_to(fg)
        fg.add_to(m)
    add(parcels, "Real parcels (FDOR)", {"color": "#334155", "weight": .4, "fillOpacity": .05}, tip=["PARCEL_ID", "PHY_ADDR1"])
    add(tx.clip(parcels.total_bounds.tolist() and mains.union_all().buffer(15000).envelope), "Real transmission (HIFLD)", {"color": "#facc15", "weight": 2, "dashArray": "6"}, tip=["ID", "OWNER", "VOLTAGE"])
    add(mains, "SYNTHETIC water mains", {"color": "#38bdf8", "weight": 2}, tip=["main_id", "diameter_in", "material", "install_year", "qc_injected"])
    add(valves, "SYNTHETIC valves", {"color": "#e2e8f0", "radius": 2}, show=False, tip=["valve_id", "qc_injected"])
    add(hyd, "Real hydrants (COJ/JEA)", {"color": "#fde047", "radius": 3}, tip=["Hydrant_ID", "Facility_Owner"])
    add(gaps, "Parcels > 500 ft from hydrant", {"color": "#f59e0b", "weight": .5, "fillOpacity": .5}, tip=["PARCEL_ID", "dist_hydrant_ft"])
    add(mains[mains.main_id.isin(iso["isolated_mains"])], f"Isolation trace: break {iso['break_main']}", {"color": "#f43f5e", "weight": 6})
    add(parcels[parcels.PARCEL_ID.isin(iso["affected_parcels"])], "Isolation: affected parcels", {"color": "#f43f5e", "fillOpacity": .45, "weight": .5}, tip=["PARCEL_ID", "PHY_ADDR1"])
    for f, col in {"FDR-101": "#a78bfa", "FDR-102": "#34d399", "FDR-103": "#fb923c"}.items():
        g = prim[prim.feeder_id == f]
        if len(g): add(g, f"SYNTHETIC feeder {f}", {"color": col, "weight": 3}, show=False, tip=["seg_id", "feeder_id", "phase", "kind"])
    add(xf, "SYNTHETIC transformers", {"color": "#ffffff", "radius": 2}, show=False, tip=["xfmr_id", "feeder_id", "phase", "kva", "n_customers"])
    add(fuses, "SYNTHETIC fuses", {"color": "#ef4444", "radius": 3}, show=False, tip=["fuse_id", "feeder_id", "amps"])
    add(parcels[parcels.PARCEL_ID.isin(out["affected_customers"])], f"Outage: {out['fuse']} customers", {"color": "#c084fc", "fillOpacity": .45, "weight": .5}, show=False, tip=["PARCEL_ID", "PHY_ADDR1"])
    add(sub, "SYNTHETIC substation", {"color": "#facc15", "radius": 9}, tip=["sub_id", "name", "tie_hifld_id"])
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;top:10px;left:50px;z-index:9999;background:#0b1220cc;color:#e2e8f0;padding:8px 14px;border-radius:6px;font-family:sans-serif'>"
        "<b style='color:#38bdf8'>GeoKnight GIS</b> &middot; Jacksonville Utility Network Demo<br><small>Water mains, valves, services, and the electric distribution network are <b>SYNTHETIC</b>. Streets (TIGER), parcels (FDOR), hydrants (COJ/JEA), and transmission (HIFLD) are real.</small></div>"))
    m.save(WEB / "index.html")


if __name__ == "__main__":
    main()
