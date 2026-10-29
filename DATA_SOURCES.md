# Data sources: what I tested (2026-10-29)

Counts come from live ArcGIS REST `returnCountOnly` queries over the Duval bbox (-82.05, 30.10, -81.32, 30.59), unless a row says otherwise.

| Source | Endpoint | Layers | Terms | Downloadable? | Count | Used |
|---|---|---|---|---|---|---|
| City of Jacksonville / JEA hydrants | `maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/1` | Hydrant points (ID, owner, status, address; main size field mostly empty) | Public COJ ArcGIS service. No license is posted, so treat it as public-records data and credit City of Jacksonville / JEA | Yes | 32,697 (bbox); 206 in the study area, 355 with buffer | Yes, real |
| FDOR statewide cadastral (FL parcels) | `services9.arcgis.com/Gh9awoU677aKree0/.../Florida_Statewide_Cadastral/FeatureServer/0` | Parcel polygons with DOR use code, address, just value | FL DOR / FGDL public parcel data | Yes (2,000 per page) | 403,813 for CO_NO=26 (Duval); 3,054 in the study area | Yes, real |
| US Census TIGERweb | `tigerweb.geo.census.gov/.../TIGERweb/Transportation/MapServer/8` (local roads) and `/6` (secondary roads) | Road centerlines | Public domain | Yes | 29,024 local segments (bbox) | Yes, real |
| HIFLD transmission lines | `services1.arcgis.com/Hp6G80Pky0om7QvQ/.../Electric_Power_Transmission_Lines/FeatureServer/0` | Lines with owner, voltage, SUB_1/SUB_2 | HIFLD Open (public) | Yes | 132 intersecting the Duval bbox | Yes, real |
| HIFLD electric substations | `.../Electric_Substations/FeatureServer` | n/a | n/a | **No.** Returns "Invalid URL"; the public substation layer is no longer at the HIFLD Open org | n/a | No |
| OpenStreetMap via Overpass | overpass-api.de, kumi.systems, mail.ru mirrors | power=substation/line/pole, emergency=fire_hydrant | ODbL | **Blocked from this box** (SSL EOF, timeouts, 504) | not measured | No. Fetch code tries it and skips cleanly; Geofabrik Florida PBF is the fallback |
| COJ `maps.coj.net/coj/rest/services` (other folders) | Utilities, SepticTanks/STPO_Public, etc. | "Utilities" folder holds only geometry and print tools; STPO has septic phase-out areas | Public | Yes | not counted | Not yet. STPO is a good sewer-context layer |
| JEA GIS (`gis.jea.com`) | n/a | n/a | n/a | **No response** (connection failed) | n/a | No |
| FDEP (`ca.dep.state.fl.us/arcgis/rest/services`) | reachable (HTTP 200) | Not browsed in depth. Candidates: wastewater facilities, reuse | Public | Probably | not counted | Future |
| FEMA NFHL (`hazards.fema.gov/arcgis/rest/services`) | reachable (HTTP 200) | Flood zones | Public domain | Probably | not counted | Future (asset flood exposure) |
| FGDL / SJRWMD | fgdl.org (redirects), SJRWMD open data | Statewide and district layers | Public | Yes (SJRWMD already pulled in another project) | not counted | Future |

## Gaps
- **No public JEA water, sewer, reclaimed, or electric-distribution pipe and wire networks.** These are treated as critical-infrastructure data and are not published. Every main, valve, service, primary, transformer, and drop in this repo is therefore **synthetic**.
- No public substation points (HIFLD layer gone, OSM blocked from here). The substation in this repo is synthetic and tied to the nearest real HIFLD line.
