# Representative Site Planner study

`study-input.json` is a reviewed, **not-yet-run** input set. Its coordinates are
synthetic and its radio settings are propagation-model inputs, not permission to
transmit. This repository must not contain invented planner output.

To complete the study:

1. Open <https://site.meshtastic.org/> and enter every value from
   `study-input.json` exactly.
2. Run the 5 km coverage prediction and export it as GeoJSON.
3. Open the point-to-point tool, use the receiver coordinates from the input,
   and save a screenshot that visibly includes terrain profile, line of sight,
   Fresnel clearance, received power, and link margin.
4. Run `capture-site-study.ps1` with the two unedited downloads, UTC run time,
   browser version, and the displayed coverage/P2P summaries. The tool validates
   the synthetic study area, copies the artifacts, hashes them, writes the
   manifest, and refuses overwrites. Never alter an export to improve a result.

Example (replace the paths and observed summaries):

```powershell
.\hardware\simulation\scripts\capture-site-study.ps1 `
  -CoverageGeoJson C:\Users\you\Downloads\coverage.geojson `
  -PointToPointPng C:\Users\you\Downloads\point-to-point.png `
  -RunAt 2026-07-30T10:00:00Z `
  -Browser "Firefox 141" `
  -CoverageSummary "Enter the displayed coverage statistics" `
  -PointToPointSummary "Enter displayed LOS, Fresnel, received power and margin"
```

The official planner documentation says it uses a browser-local ITM/SPLAT!
model with SRTM terrain. It also states that obstructions other than terrain,
including trees and buildings, are not modelled. These limitations must remain
beside every demo claim.
