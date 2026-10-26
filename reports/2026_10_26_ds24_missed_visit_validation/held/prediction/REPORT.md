# Held-recording forecast preparation

The fixed twelve-recording panel contains 288 paired windows and 576 receiver
cells. All requested native target metadata is available. Exact R01 produces
454 available forecasts and retains 122 `no_donor` cells. The unchanged R02
primary transformation qualifies 249 quadratic forecasts, falls back to the
consistent linear forecast in 205 cells and retains the same 122 no-donor cells.
These are earlier-history opportunities, not target detections or accuracy
measurements. No target response diagnostic, IQ read, score or geography was
used in this preparation.

| Recording | Cells | R01 available | No donor | R02 quadratic | R02 linear fallback |
|---|---:|---:|---:|---:|---:|
| DS24-0015 | 48 | 42 | 6 | 31 | 11 |
| DS24-0016 | 48 | 46 | 2 | 34 | 12 |
| DS24-0019 | 48 | 45 | 3 | 16 | 29 |
| DS24-0075 | 48 | 26 | 22 | 19 | 7 |
| DS24-0077 | 48 | 27 | 21 | 22 | 5 |
| DS24-0081 | 48 | 36 | 12 | 7 | 29 |
| DS24-0083 | 48 | 37 | 11 | 18 | 19 |
| DS24-0085 | 48 | 39 | 9 | 5 | 34 |
| DS24-0089 | 48 | 40 | 8 | 20 | 20 |
| DS24-0091 | 48 | 39 | 9 | 27 | 12 |
| DS24-0093 | 48 | 38 | 10 | 28 | 10 |
| DS24-0095 | 48 | 39 | 9 | 22 | 17 |
| Total | 576 | 454 | 122 | 249 | 205 |

Selection uses the original CH1/4 controls and CH5–8 panel, four counter
fractions and both receivers. Sources and panel were frozen before forecast
generation. The predictor imports are hash-bound to the original published
R01 and R02 source protocols. R01 modes, rank limits, gates, uncertainty and
fallback are unchanged; R02 keeps the original primary and CFO, applying only
its previously sealed conservative timing transformation. R01 point/search
and R02 controls are separate methods, with no target-wise best-method choice.

Original tracking exports were parsed for metadata and strictly earlier donor
histories. Target candidate responses are excluded from target panel fields;
no target evaluation archive was created. An earlier panel target may later
enter history through its original acquisition result, exactly as before.
Recovered forecasts or measurements never become donors. The recordings were
exposed to earlier studies and share the existing site; they are held out from
this revision, not a new-site generalization test.

The mandatory JSON serialization/reload before the original enrichment helper
preserves donor object boundaries. All stream-generation labels remain
separate from integer hardware generation. Three owned tests pass, covering
selection independence from candidate values, bounded earlier-only history
with deterministic ties, and the actual enrichment alias regression. The
complete audit passes fresh exact R01/R02 forecasts and target-field redaction
for all 576 cells, native mapping for all twelve channel/receiver pairs, and
native metadata for 1,395 selected donor windows. All 454 available primary
forecasts retain exact donor/CFO provenance and exact legacy-adapter parity.
Generation took 5.8 s and the full forecast audit 3.9 s, with BLAS1 and a
580 s command bound. No new paired detector replay or public IQ-reader
exhaustion was performed; those belong to a separately authorized raw stage.

Use `r01_prediction_packets.json` for unchanged R01 scoring. Use
`r02_predictions.json` for the separate R02 consistent-linear,
quadratic/fallback and descriptive legacy controls. R02 historical epochs are
nominal midpoint-effective constant estimates; its output epoch is already
expressed relative to target origin. The original R01 adapter's extra midpoint
advance remains distinct. See `INTERFACE.md` and the original R02 convention
notes before scoring. No scoring authority is issued by these forecast seals.

Application protocol SHA256:
`9c193b9897f9864731ed9f30c5256a531fabffa00d9572333a044a2aa11f379b`.
Panel SHA256:
`0683c4b3c4998d0bbdc01c94b2f716740762b37aa8b405093b6d28e01ab17509`.
R01 packet SHA256:
`a6aa174b48fc89088ebeb00640affdc903caa8757e25d24532024c29e525b588`.
R02 forecast SHA256:
`29ed41e90f05074f3cd4a1fa2f797eb1d3f11845605c718db1389cda6d856c99`.
Separate `r01_forecast_seal.json` and `r02_forecast_seal.json` bind both
methods. `verification.json`, example packets and the final
`artifact_seal.json` provide the complete handoff.
