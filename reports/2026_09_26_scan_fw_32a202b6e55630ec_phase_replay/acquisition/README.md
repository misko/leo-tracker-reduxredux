# Corrected acquisition replay

This package pins the numerical replay to `e1a24b200d4bb68d4f38484dc591e9b9616a2e70`
and the capture manifest to
`sha256:b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a`.
All work is read-only against the recording.

## Persisted producer resolution

The v8 product does not carry a release SHA in its public binding. The producer
is nevertheless resolved from deployment evidence:

- The product binding was published at 2026-09-26 12:31:03 UTC, immediately
  after the session was imported and queued in the system journal.
- `leo-adaptive-analysis-worker@.service` was running the immutable executable
  `/opt/leo-tracker/releases/2c30eaf50064623a666e1c078c56a02cb3223a70/.venv/bin/python`.
- That directory's `.leo-release-source.json` declares revision `2c30eaf5...`
  and tree `2327b562456f09d3227c1acbbd53fb5605111a33`.
- Geometry repair `847ebcaf...` and presentation repair `554e8403...` are both
  ancestors of `2c30eaf5...`. There is no diff from that release to the replay
  head in `acquisition.py`, `detector.py`, `pilot_search_geometry.py`, or
  `adaptive_hop_analysis.py`.
- A fresh corrected replay of visit 0 reproduced the persisted candidate values
  exactly. It took 5.70 seconds with one numerical thread.

The persisted rows are therefore admitted as the corrected sparse first-20-ms
census, rather than called legacy evidence. The 0.025 margin remains a historical
comparison gate, not a calibrated false-alarm probability.

## Census and coordinates

Every one of 2,214 visit envelopes and its canonical content digest was checked.
The export contains 20,059 complete fractional candidates. RX0 passed the
comparison gate in 687 visits, RX1 in 856, both in 577, and neither in 1,248.

`candidate-inventory.csv` keeps these coordinates distinct:

- `acquired_absolute_baseband_cfo_hz`: the actual mixer coordinate returned by
  acquisition;
- `glrt_residual_cfo_hz`: GLRT refinement relative to that acquisition point;
- `tracking_absolute_baseband_cfo_hz`: acquired plus residual, still in the
  tuner-baseband coordinate used for coherent mixing;
- pilot-relative raw and canonical display CFO, plus the explicit alias lift.

The verified v14 candidate-only tracking product is exported verbatim by field
in `track-inventory.json`. It binds the same capture and GLRT metrics manifest;
it claims neither emitter identity nor a position fix.

## RF validity and dense replay

The completed capture audit found zero counter-word rows across all 2,214
digest-verified chunks. Raw and RF-valid scoring are therefore the same dataset
for this scan: no zero fill, interpolation, deletion, or compacting was applied.
The raw/valid side of the planned 2x2 comparison collapses exactly. Any later
filter must still expand invalid support if another invalid class is identified.

The authoritative cohort is `../selection.json`, digest
`sha256:b73c0d5322a6a70c6ee851ee80ad99ef62ca13b190ae4bdeb35ce95ce2030115`.
`run_primary_acquisition.py` checkpoints all six disjoint 20-ms probes per
selected dwell to bulk scratch. Each result preserves every retained basin and
both receivers. It does not choose a pilot from phase strength.

## Mechanism ablations

Four bounded variants ran on the same sealed eight-visit smoke cohort. Tuning
only, physically clipped wider coverage, peer-missing fallback anchors, and a
22-basin shortlist each recovered the same five visits. They retained 14, 13,
15, and 18 passing candidates respectively. Median runtimes were 6.70, 29.22,
10.95, and 8.76 seconds. Thus fallback added one basin and the larger shortlist
kept four more without recovering another visit; wider coverage cost 4.4 times
as much as tuning-only and retained one fewer passing basin. These isolate
bounded mechanisms on fixed metadata; they are not calibrated detection-rate
comparisons.

## Verification

The geometry, detector, batch/scalar parity, native-rate acquisition, and
parallel adaptive analysis suites passed: 109 tests total across the focused
runs. The report-owned tests and Ruff checks also pass. The scalar parity suite
covers both edges and native 10 MS/s, candidate permutations, zero/duplicate
inventories, and the production-window scalar fallback.
