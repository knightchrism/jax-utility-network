# GeoKnight GIS | Topology QC Report: Avondale/Riverside, Jacksonville FL

> **SYNTHETIC NETWORK.** Water and distribution-electric assets are synthetic, generated on real Census TIGER streets and real FDOR parcels. Some defects were planted on purpose (`qc_injected=1`) to check that the QC catches them. Hydrant locations are real (City of Jacksonville / JEA service).

| Network | Check | Count | Feature IDs (truncated) |
|---|---|---:|---|
| Water | Disconnected main islands (components beyond the main network) | 3 | WM00145, WM00148, WM00149, WM00150, WM80000, WM80001 |
| Water | Disconnected mains (count) | 6 |  |
| Water | Dead ends (degree-1 nodes; many are legitimate cul-de-sacs) | 91 |  |
| Water | Short dangling segments < 60 ft (likely digitizing error) | 17 | WM00019, WM00073, WM00145, WM00150, WM00341, WM00445, WM00464, WM00465, WM00650, WM00893, WM01142, WM01155, WM01193, WM01208, WM01281 |
| Water | Mains missing diameter | 6 | WM00764, WM00773, WM00810, WM00850, WM01301, WM01330 |
| Water | Duplicate main geometry | 2 | WM90000, WM90001 |
| Water | Valves not on a main (> 0.5 ft) | 3 | WV90000, WV90001, WV90002 |
| Electric | Primary segments unreachable from substation | 0 |  |
| Electric | Unconnected transformers (> 1 ft from primary / no segment) | 2 | XF9001, XF9002 |
| Electric | Transformers missing phase | 2 | XF00257, XF00299 |
| Electric | Transformers missing voltage | 2 | XF00293, XF00426 |
| Electric | Primary segments missing phase | 3 | PRI00005, PRI00324, PRI00374 |
| Sewer | Adverse (negative) slope | 5 | SM00172, SM00192, SM00324, SM00379, SM00518 |
| Sewer | Below minimum slope for diameter (10 States) | 0 |  |
| Sewer | Flow loops (directed cycles) | 1 | SM99001->SM00358 |
| Sewer | Orphan manholes (no connected main) | 3 | MH99000, MH99001, MH99002 |
| Sewer | Slope > 10% (review for drop manhole; DEM artifacts possible) | 41 |  |
| Sewer | Manholes deeper than 20 ft (consider extra lift station) | 139 |  |

## Main-break valve isolation
- Break on **WM00645**: close **4 valves** (WV00373, WV00374, WV00424, WV00425)
- Isolated mains: 5; **affected parcels: 5**

## Fuse outage trace
- Fuse **FU0004** on FDR-101 operates: 25 transformers, **139 customers out**
- Customers per feeder (breaker-level outage): {'FDR-101': 1110, 'FDR-102': 937, 'FDR-103': 742}

## Hydrant coverage (real hydrants)
- 0 of 2789 parcels (0.0%) are > 500 ft (straight line) from the nearest hydrant.

## Hydrant coverage: Northside study area (real hydrants, real parcels)
- **342 of 2671 parcels (12.8%) are > 500 ft** from a hydrant; 107 are > 1,000 ft (max 2380 ft).

## Sewer traces (synthetic)
- Parcels draining to each lift station: {'LS-1': 337, 'LS-2': 1823, 'LS-3': 629}
- Longest downstream trace: MH00160 to LS-2, 33 manholes, 7543 ft
