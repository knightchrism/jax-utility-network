# GeoKnight GIS: Jacksonville Utility Network Demo

**Water, sewer, and electric network topology, QC, valve-isolation, outage and sewershed traces, and hydrant coverage for Jacksonville FL (Avondale/Riverside and Northside).**
By Christopher Knight · [knightchrism.github.io](https://knightchrism.github.io) · GitHub [@knightchrism](https://github.com/knightchrism)

> ⚠️ **Synthetic network data.** JEA does not publish its pipe or wire networks. Every water main, valve, service line, meter, sewer main, manhole, lift station, primary conductor, fuse, transformer, service drop, and the substation in this repo is **synthetic**: generated on real streets and parcels, and labeled `synthetic_*` in every filename and layer. Real inputs are labeled `real_*`.

![map](outputs/jax_utility_network_map.png)

## Problem
Utility GIS teams keep connected network models current and use them to answer operational questions: *Which valves isolate a main break? Who loses power when this fuse operates? Which parcels are too far from a hydrant? Where is the network topologically broken?* This repo answers those questions end to end with an open Python stack.

## Data sources and licenses
| Layer | Source | Status |
|---|---|---|
| Street centerlines | US Census TIGERweb (public domain) | real |
| Parcels (2,789 in the study area) | FL Dept. of Revenue statewide cadastral (public) | real |
| Fire hydrants (206 in the study area, 32,697 countywide) | City of Jacksonville / JEA hydrant service (public ArcGIS REST) | real |
| Transmission lines (132 in the Duval bbox) | HIFLD Open | real |
| Power lines, substations, poles (Duval) | OpenStreetMap through the Geofabrik Florida extract (ODbL, © OpenStreetMap contributors) | real |
| Septic tank phase-out areas (4) | City of Jacksonville STPO service | real |
| Bare-earth DEM (sewer rim elevations) | USGS 3DEP (public domain) | real |
| Northside parcels (2,671) and hydrants (318, buffered) | FDOR / COJ-JEA | real |
| Sewer mains, manholes, lift stations, laterals | generated | **synthetic** |
| Water mains, valves, services, meters, hydrant laterals | generated | **synthetic** |
| Substation, feeders, fuses, transformers, service drops | generated | **synthetic** |

Endpoint tests, counts, and gaps are in [DATA_SOURCES.md](DATA_SOURCES.md).

## Methods
1. **Fetch** (`jaxnet-fetch`): paged ArcGIS REST queries into `data/raw/` (gitignored).
2. **Build** (`jaxnet-build`): node the TIGER streets at intersections, then lay the network on top:
   - Water mains follow the centerlines. A valve goes on every leg 20 ft from each intersection. Each FDOR parcel gets a service line and meter tapped to the nearest main. The real hydrants are snapped to the mains with laterals.
   - Electric starts from a synthetic substation tied to the nearest real HIFLD line. A radial minimum spanning tree over the streets gives the primary, split into 3 balanced feeders. Trunk segments are 3-phase and laterals are single-phase, with fuses at the lateral taps. Transformers serve about 6 customers each, with a service drop to every parcel.
   - Sewer: manholes go at intersections and every 350 ft, with rim elevations from 3DEP. Flow follows a shortest-path tree to 3 lift stations placed at local low points, with uphill runs penalized. Inverts are set from the top of each branch down to the outlet, with 6 ft minimum cover and 10 States minimum slopes (0.40% for 8-inch pipe). Pipe diameter grows with the upstream area served, and every parcel gets a lateral.
   - QC defects are planted on purpose and flagged `qc_injected=1`.
3. **Analyze** (`jaxnet-analyze`), built on networkx graphs:
   - Topology QC: disconnected islands, short dangles, missing diameter, duplicate geometry, valves off a main, unconnected transformers, missing phase or voltage.
   - Main-break valve isolation: a graph walk outward from the break that stops at valves.
   - Fuse outage: downstream walk on the directed radial feeder.
   - Sewer QC: adverse slope, below-minimum slope, flow loops (directed cycles), orphan manholes, steep reaches, deep manholes. Sewer traces: the parcels draining to each lift station, plus the longest upstream-to-outlet downstream trace.
   - Hydrant coverage (both study areas): parcels more than 500 ft (straight line) from a real hydrant, counting hydrants up to about 1,000 ft outside the study area to avoid edge effects.

## Run it
```bash
uv sync
uv run jaxnet-fetch     # real ArcGIS REST data and 3DEP DEM -> data/raw (about 4 min)
uv run jaxnet-osm       # Geofabrik Florida PBF (660 MB) -> OSM power clipped to Duval (about 4 min)
uv run jaxnet-build     # synthetic networks -> data/processed/jax_utility_network.gpkg + data/synthetic/*.geojson
uv run jaxnet-analyze   # QC + traces -> outputs/, web/index.html
```

## Outputs
- `web/index.html`: interactive Leaflet map with toggleable layers
- `data/processed/jax_utility_network.gpkg`: all layers plus trace results (regenerated; gitignored)
- `data/synthetic/*.geojson`: synthetic network layers (committed)
- `outputs/qc_report.md`, `outputs/results.json`, `outputs/jax_utility_network_map.png`

## Results
| Metric | Value |
|---|---|
| Synthetic water | 1418 main segments, 848 valves, 2789 services and meters |
| Synthetic electric | 416 primary segments in 3 feeders, 82 fuses, 629 transformers, 2789 service drops |
| Synthetic sewer | 611 gravity mains, 616 manholes, 3 lift stations, 2789 laterals |
| Real OSM power (Duval) | 1712 lines, 117 substations, 11122 poles, towers and transformers |
| Water QC | 6 disconnected mains, 17 short dangles, 6 missing diameter, 2 duplicates, 3 valves off main |
| Electric QC | 2 unconnected transformers; missing phase on 2 transformers and 3 primary segments; 2 missing voltage |
| Sewer QC | **5 adverse slopes, 1 flow loop, 3 orphan manholes**; 41 steep reaches (check for drop manholes); 139 manholes deeper than 20 ft (consider another lift station) |
| Main break WM00645 | close 4 valves, 5 mains out, **5 parcels without water** |
| Fuse FU0004 (FDR-101) | 25 transformers, **139 customers out**; feeders carry FDR-101: 1110, FDR-102: 937, FDR-103: 742 |
| Sewersheds | LS-1: 337, LS-2: 1823, LS-3: 629 parcels; longest downstream trace runs 33 manholes and 7543 ft to LS-2 |
| Hydrant coverage, Avondale/Riverside (real) | 0 of 2789 parcels > 500 ft (dense grid) |
| Hydrant coverage, Northside (real) | **342 of 2671 parcels (12.8%) > 500 ft**; 107 > 1,000 ft; max 2380 ft |

Hydrant distance is straight-line from the parcel's interior point. Large undeveloped parcels raise the Northside numbers, so read gaps as candidates for field review, not deficiencies. Full details: [outputs/qc_report.md](outputs/qc_report.md)

## Roadmap
- Load into PostGIS with pgRouting for SQL-side traces (PostgreSQL client is on the box; no server is running yet)
- Reclaimed water network
- Network-distance (along-street) hydrant coverage
- FEMA flood-zone exposure of assets

---
GeoKnight GIS · Christopher Knight
