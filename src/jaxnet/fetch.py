"""Fetch REAL public data for the study area into data/raw/ (gitignored)."""
import json, sys
import requests
import geopandas as gpd
from .config import RAW, AOI, AOI2, DUVAL, SOURCES, OVERPASS

UA = {"User-Agent": "geoknight-gis-jax-utility-demo/0.1 (portfolio)"}


def env(b):
    return {"geometry": ",".join(map(str, b)), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}


def count(url, bbox, where="1=1"):
    r = requests.get(f"{url}/query", params={**env(bbox), "where": where, "returnCountOnly": "true", "f": "json"}, headers=UA, timeout=60)
    return r.json().get("count")


def arcgis(url, bbox, where="1=1", fields="*", page=1000):
    feats, off = [], 0
    while True:
        p = {**env(bbox), "where": where, "outFields": fields, "outSR": 4326, "f": "geojson",
             "resultOffset": off, "resultRecordCount": page}
        js = requests.get(f"{url}/query", params=p, headers=UA, timeout=120).json()
        fs = js.get("features", [])
        feats += fs
        if len(fs) < page:
            break
        off += page
    return gpd.GeoDataFrame.from_features(feats, crs=4326)


def overpass(q):
    for ep in OVERPASS:
        try:
            r = requests.post(ep, data={"data": q}, headers=UA, timeout=90)
            if r.ok:
                return r.json()
        except Exception as e:  # noqa
            print("  overpass fail", ep, e)
    return None


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    counts = {}
    jobs = {
        "hydrants": (SOURCES["hydrants"], "Hydrant_ID,Facility_Owner,JFRD_Main_Size,JFRD_Hydrant_Status,Address"),
        "parcels": (SOURCES["parcels"], "PARCEL_ID,CO_NO,DOR_UC,PHY_ADDR1,JV,NO_RES_UNT"),
        "roads": (SOURCES["roads"], "NAME,MTFCC"),
        "roads_secondary": (SOURCES["roads_secondary"], "NAME,MTFCC"),
    }
    for name, (url, fields) in jobs.items():
        where = "CO_NO=26" if name == "parcels" else "1=1"
        counts[f"{name}_duval_bbox"] = count(url, DUVAL, where)
        g = arcgis(url, AOI, where, fields)
        g.to_file(RAW / f"{name}_aoi.geojson", driver="GeoJSON")
        counts[f"{name}_aoi"] = len(g)
        print(name, counts[f"{name}_duval_bbox"], "in Duval bbox;", len(g), "in AOI")
    # hydrants in AOI + ~1,000 ft buffer, to avoid edge effects in the 500 ft coverage test
    bb = (AOI[0] - .004, AOI[1] - .003, AOI[2] + .004, AOI[3] + .003)
    arcgis(SOURCES["hydrants"], bb, fields="Hydrant_ID,Facility_Owner").to_file(RAW / "hydrants_aoi_buffered.geojson", driver="GeoJSON")
    tx = arcgis(SOURCES["transmission"], DUVAL, fields="ID,OWNER,VOLTAGE,VOLT_CLASS,STATUS,SUB_1,SUB_2")
    tx.to_file(RAW / "hifld_transmission_duval.geojson", driver="GeoJSON")
    counts["hifld_transmission_duval_bbox"] = len(tx)
    print("transmission", len(tx))
    b = DUVAL
    q = f"[out:json][timeout:80];(nwr[power=substation]({b[1]},{b[0]},{b[3]},{b[2]}););out center tags;"
    js = overpass(q)
    if js:
        json.dump(js, open(RAW / "osm_substations_duval.json", "w"))
        counts["osm_substations_duval_bbox"] = len(js["elements"])
    else:
        counts["osm_substations_duval_bbox"] = None
        print("  Overpass unreachable; OSM power layers skipped (see README).")
    counts.update(fetch_phase2())
    json.dump(counts, open(RAW / "fetch_counts.json", "w"), indent=2)
    print(json.dumps(counts, indent=2))


def fetch_dem(bbox, out, size=(900, 700)):
    """USGS 3DEP bare-earth DEM (public domain) as GeoTIFF, EPSG:4326, metres."""
    p = {"bbox": ",".join(map(str, bbox)), "bboxSR": 4326, "imageSR": 4326, "size": f"{size[0]},{size[1]}",
         "format": "tiff", "pixelType": "F32", "interpolation": "RSP_BilinearInterpolation", "f": "image"}
    r = requests.get(SOURCES["dem_3dep"] + "/exportImage", params=p, headers=UA, timeout=180)
    r.raise_for_status()
    out.write_bytes(r.content)


def fetch_phase2():
    c = {}
    fetch_dem(AOI, RAW / "dem_3dep_aoi.tif")
    st = arcgis(SOURCES["septic_phaseout"], DUVAL)
    st.to_file(RAW / "septic_phaseout_areas.geojson", driver="GeoJSON"); c["septic_phaseout_areas"] = len(st)
    bb = (AOI2[0] - .004, AOI2[1] - .003, AOI2[2] + .004, AOI2[3] + .003)
    p2 = arcgis(SOURCES["parcels"], AOI2, "CO_NO=26", "PARCEL_ID,CO_NO,DOR_UC,PHY_ADDR1,JV,NO_RES_UNT")
    p2.to_file(RAW / "parcels_aoi2.geojson", driver="GeoJSON"); c["parcels_aoi2"] = len(p2)
    h2 = arcgis(SOURCES["hydrants"], bb, fields="Hydrant_ID,Facility_Owner")
    h2.to_file(RAW / "hydrants_aoi2_buffered.geojson", driver="GeoJSON"); c["hydrants_aoi2_buffered"] = len(h2)
    print(c)
    return c


if __name__ == "__main__":
    sys.exit(main())
