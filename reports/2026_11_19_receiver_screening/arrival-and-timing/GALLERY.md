# Arrival and timing gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery contains 14 position comparisons in two calibration settings and 10 standalone stage charts. The 28 position pages retain the same scheduled recordings or offers in both views and have 392 audit rows in [positions.csv](positions.csv). Stage charts retain their own measured detector, timing, or queue boundaries. Each PNG and its measurement table are indexed in [chart-inventory.csv](chart-inventory.csv).

When the receiver makes a terminal withholding decision before numerical refinement, the position comparison counts the withheld offer and the inventory gives its recorded reason. Both geographic values stay blank.

## Rebuild the offline gallery

```sh
evidence=reports/2026_11_19_receiver_screening/arrival-and-timing
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts"
```

Open the generated `index.html` or the copy in `modification-charts.zip`. Each included stage has a measurement table, and each included position comparison has both calibration views. The archive’s `artifact-sha256.json` checks the extracted files.

## Newly measured roof references

DS29-0047 is a newly replayed recording from the existing surveyed DS29 roof. The fresh-replay and fresh-paced-adaptive comparisons use all four original v5 policies rerun on its authenticated capture-era factors and causal catalogue.

A roof chart can include a newly measured recording through the optional `roof_references` field of its `figures.json` descriptor. Give it the local `authority` and `predictions` basenames and bind both in the ordinary figure receipt. The authority has a `cases` array containing the newly measured IDs, recording and group names, surveyed coordinates, and the shared `paired_capture_sha256`, `catalog_sha256`, and offered `tile` in `bindings`. Other common fields, such as an authenticated capture manifest, can also be bound.

The prediction archive contains one measured row for each original v5 role and each new case. Use `baseline`, `selective-gap`, `omitted-track-one`, and `omitted-tracks` as the `method` values. Rows carry the same shared bindings and the actual capture-era `native_sha256`. Position errors are computed from the sealed coordinates. Withheld, failed, and timed-out original trials keep their recorded outcome.

For a combined chart, the local sidecars cover the new case IDs. The other scheduled IDs are resolved through their existing sealed roof references.
