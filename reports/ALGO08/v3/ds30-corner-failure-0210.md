# DS30-0210 fixed on nominal phase support after the same installed corner failure

The installed DS30-0210 and DS30-0397 solver failures produced **byte-identical exception traces**. Both failed during the shifted receiver-smooth corner lookup in initial ranking, before either calibration fit. The successor completed both recordings. **DS30-0210 used the original nominal support**, with zero added knots or SGP4 calls, while **DS30-0397 used four live extensions**. The second fix establishes another successful successor outcome and a different observed mechanism from the earlier support repair. [Machine receipt](measurements/ds30-corner-failure-0210.json.gz) · [Earlier DS30-0397 audit](ds30-0397-orbit-support-audit.md)

## Same installed failure, different candidate path

Both installed stderr files hash to `2b2c08ae3926f1f20fce12cf4bdce96e36dfc7ef38b7bca25b53800529270442` and match the original paired failure receipts. On each recording, the first exception and the installed retry pass through `v5_core.ranked_initial_nodes`, `discovery.explore`, `ScanLikelihood.association`, `ScanLikelihood.predictions`, the instance's sparse `shifted`, and `orbit_projector.prepare`. The projector rejects the shifted interpolation domain with `ValueError: orbit phase interpolation never extrapolates`. The installed retry enters the older support wrapper, but its class-level patch is shadowed by the sparse `shifted` already on the scan instance. Both installed workers exit 1 without a terminal, position, RF fit, owners or figures. The traces carry no offending phase, satellite row, side of the interval or query timestamp.

| Recorded successor evidence | DS30-0210 | DS30-0397 |
| --- | ---: | ---: |
| Issued / admitted stereo visits | 6,770 / 6,713 | 6,773 / 6,375 |
| Signed selected 20/8 ms factors | 7,191 | 5,725 |
| Route / reason | `lean` / `healthy_samples` | `lean` / `healthy_samples` |
| Paid centres / original corners / ranked nodes | 2 / 4 / 6 | 2 / 4 / 6 |
| Catalogue rows / curved tracks at rank | 1,523 / 111 | 1,296 / 84 |
| Inference calls / whole-solver restarts | 1 / 0 | 1 / 0 |
| Live extended projections / SGP4 calls / added states | 0 / 0 / 0 | 4 / 4 / 1,116 |
| Added support knots, seconds relative to orbit origin | None | −26 through −18 |
| Terminal orbit policy | `stock` | `orbit_support` |

The successor uses the frozen instance-level binding capable of extending the causal bank during the actual corner lookup. On 0210 it evaluated all four nominal corners and completed the rank with three distinct finalists, no ordinary-rank retry, zero live support wall and zero augmented bank bytes. Its actual candidate path used the available nominal domain. On 0397 the binding added nine one-second knots and kept the strict projector at unchanged successor query times and phases. For 0210, the sealed records cannot attribute the avoidance to one decision. Within each pair the physical input, signed visit counts, archive authority and offered region agree, while installed 20 ms and successor 20/8 ms packets have different hashes and enter different ranking procedures. No same-packet experiment holds either input or discovery policy fixed. The record establishes early phase failure for installed and nominal-support success for the actual candidate, with no individual offending input or counterfactual identified.

## Both calibrated outcomes and verification

Horizontal errors use the original eligible, signed site reference. Conditional RF RMS and all-owner RF RMS are separate from geographic error. Each candidate uses the same ordered owner and role roster across its own two calibration arms.

| Recording | Calibration | Latitude, longitude | Horizontal error | Conditional / all-owner RF RMS | Owners |
| --- | --- | --- | ---: | ---: | ---: |
| DS30-0210 | Fixed `c = 0` | 37.848152827, −122.489695151 | 0.360258 km | 152.317 / 177.623 Hz | 4,507 |
| DS30-0210 | Fitted `c` | 37.849175094, −122.490659216 | 0.430816 km | 152.207 / 169.292 Hz | 4,507 |
| DS30-0397 | Fixed `c = 0` | 37.849172776, −122.477373088 | 0.736061 km | 139.860 / 169.113 Hz | 3,242 |
| DS30-0397 | Fitted `c` | 37.850329997, −122.475891592 | 0.877525 km | 139.692 / 147.721 Hz | 3,242 |

The fitted endpoint on 0210 moved **141.727 m** and increased survey error by **70.558 m**. Conditional RF RMS fell **0.110 Hz** and all-owner RF RMS fell **8.330 Hz**. On 0397 the corresponding geographic movement was **182.971 m** and its error increased **141.464 m**. Each original candidate has a complete 179-location shared grid with finite scores in both arms and zero endpoint replay discrepancy. Its path and grid numerics rehash and bind the original terminal, its signed detector digest, both owner maps and the position image. Each application receipt verified all eight PNGs with zero fallback. The independently charged publication verifier recorded matching encoded and decoded RGBA digests and dimensions for all eight. This audit checked those receipts without reopening image payloads.

## Original paid timing

| Recording and outcome | Worker elapsed / CPU | Separate verifier elapsed | Originally charged elapsed / CPU |
| --- | ---: | ---: | ---: |
| DS30-0210 installed solver failure | 102.262 / 91.152 s | 0.112 s failure diagnostic, outside charged time | 102.262 / 91.152 s |
| DS30-0210 successor verified fix | 68.414 / 63.990 s | 0.567 s | 68.981 / 64.557 s |
| DS30-0397 installed solver failure | 90.017 / 77.353 s | 0.084 s failure diagnostic, outside charged time | 90.017 / 77.353 s |
| DS30-0397 successor verified fix | 60.621 / 58.355 s | 0.523 s | 61.143 / 58.878 s |

The original summed elapsed is **192.278 s installed** to two failed exits and **130.125 s successor** to two independently verified fixes. Both failures stay in timing and outcome denominators. These clocks compare the actual different outcomes and give no successful-pair speedup. DS30-0210 ran successor-first across separate leases, while DS30-0397 ran installed-first in one lease. Neither case supplied installed position error or RF fit.

The audit used only sealed metadata, sidecars, source and the stored verifier receipts. No waveform, ephemeris or PNG payload was opened and no pipeline ran. Three new focused tests and three prior failure-audit tests passed. The expanded JSON SHA-256 is `8a7018db92c4f79dd884fcd4337c3444b9d7a700b134f5752bef5d2ed82079cc`. Run `python -B reports/ALGO08/v3/ds30_corner_failure_0210.py CAMPAIGN_ROOT` with permission to read both sealed case directories. [Read-only audit](ds30_corner_failure_0210.py) · [Component tests](../../../tests/pipeline_eval/test_ds30_corner_failure_0210.py)
