"""Shared config. Study area = Avondale/Riverside, Jacksonville FL (real streets + parcels)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
SYN = ROOT / "data" / "synthetic"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
WEB = ROOT / "web"

# lon/lat bbox: Avondale / Riverside neighborhood
AOI = (-81.7160, 30.2985, -81.6960, 30.3135)
# Second study area: Northside (Dunn Ave / Lem Turner area), sparser hydrants
AOI2 = (-81.7000, 30.4400, -81.6700, 30.4650)
# Duval County approx bbox (for county-level counts / transmission)
DUVAL = (-82.05, 30.10, -81.32, 30.59)
CRS_FT = "EPSG:2236"  # NAD83 / Florida East (US ft)

SOURCES = {
    "hydrants": "https://maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/1",
    "parcels": "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0",
    "roads": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/8",
    "roads_secondary": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/6",
    "septic_phaseout": "https://maps.coj.net/coj/rest/services/SepticTanks/STPO_Public/MapServer/0",
    "dem_3dep": "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer",
    "transmission": "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0",
}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
GEOFABRIK_FL = "https://download.geofabrik.de/north-america/us/florida-latest.osm.pbf"
