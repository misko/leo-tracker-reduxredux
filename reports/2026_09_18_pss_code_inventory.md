# PSS report and code inventory

This inventory reviews the committed PSS implementation and the reports that
established it. Dates are the latest Git commit dates for each path, not local
filesystem modification times. Reference repositories and frozen report source
trees are not runtime dependencies.

## Current architecture

There are two related PSS paths:

1. **Standard-native PSS** is integrated into the offline Standard analysis
   topology. It projects valid native IQ, runs independent blind PSS searches,
   associates timing modes, persists an immutable candidate-only product, and
   renders PSS/GLRT comparison figures.
2. **Bandwidth-aware PSS acquisition and causal tracking** is a newer pure
   numerical stack. It models arbitrary receiver passbands and center offsets,
   performs a real blind timing search for every CFO hypothesis, and tracks
   frame phase and coarse CFO causally. It remains experimental because
   pilot-only controls can produce qualified peaks and stable tracks.

The deployed adaptive scanner currently publishes edge-pilot GLRT products and
does **not** invoke either PSS path. `tracking` in the PSS tracker means a stable
candidate hypothesis, not verified PSS, satellite identity, or absolute time of
arrival.

## Runtime and reusable code

| Latest change | Path | Role | Capabilities | Operational status |
|---|---|---|---|---|
| 2026-09-15 | `src/leo/analysis/starlink/pss_timing.py` | Core timing kernel | Exact published 1,056-sample/240 MS/s PSS construction; rate-generic subband template; FFT correlation; folded 750 Hz frame lattice; separated modes; fractional local peak refinement; per-frame windows; explicit continuity coordinates | Reusable numerical core; candidate-only |
| 2026-09-02 | `src/leo/analysis/starlink/pss_search.py` | Standard search orchestration | Validity-safe projection; coarse/fine CFO banks; independent blind and conditioned origins; mode de-duplication; timing-track association and polynomial fitting | Used by Standard-native analysis |
| 2026-09-15 | `src/leo/analysis/starlink/pss_bandwidth.py` | Bandwidth-aware acquisition | Arbitrary rates in `(0, 240 MS/s]`; asymmetric passbands; center-frequency offsets; optional measured complex receiver response; partial PSS-channel overlap; per-CFO projected templates; bounded coarse-to-fine bank | Experimental reusable module |
| 2026-09-15 | `src/leo/analysis/starlink/pss_tracker.py` | Causal candidate tracker | Source-isolated circular frame-phase and coarse-CFO Kalman filters; acquisition/tracking/coasting/lost states; prediction gates; ambiguity rejection; gap expiry; future CFO-bank suggestion | Experimental; candidate-only |
| 2026-09-02 | `src/leo/analysis/standard/native_pss.py` | Standard-native adapter | Reads validity-aware IQ; binds channel/edge reference; projects to canonical 25 MS/s when exact; blind anchors every 0.5 s; tracking banks; optional explicitly labelled GLRT-conditioned follow-up; builds persisted contract | Integrated offline production analysis |
| 2026-09-01 | `src/leo/contracts/standard_native_pss.py` | Persisted contract | Digest-bound projections, search blocks, modes, tracks, accounting, source lineage, dispositions, and candidate-only result closure | Immutable public v1 contract |
| 2026-09-06 | `src/leo/analysis/standard/native_pss_glrt_comparison.py` | Scientific comparison | Aligns native-25 PSS timing with 2.5 MS/s GLRT timing/CFO in a common sign convention and renders comparison evidence | Integrated report/presentation stage |
| 2026-09-06 | `src/leo/pipeline/standard_native.py` | Pipeline topology | Requires native PSS on the high-rate paired path and joins it to low-rate GLRT without making PSS a runtime dependency of GLRT | Integrated Standard pipeline |
| 2026-09-07 | `src/leo/analysis/standard/native_analyzers.py` | Analyzer registration | Registers `path-pss-native`, configuration digest validation, exact product requirements, and analyzer construction | Integrated Standard pipeline |
| 2026-09-06 | `src/leo/analysis/standard/native_products.py` | Product declaration | Declares `standard.pss-frame-timing` schema v1 and native-path output inventory | Integrated Standard pipeline |
| 2026-09-06 | `src/leo/application/standard_native_presentation.py` and `src/leo/presentation/standard_native_artifacts.py` | Web/report presentation | Selects PSS/GLRT comparison product versions and renders native-25 versus 2.5 MS/s figures | Integrated Standard presentation |

The reusable numerical entry point for a simple block is
`search_pss_frame_timing()`. For an offset or partly overlapping capture, use
`PssCaptureBand` with `acquire_pss_band()` or
`acquire_pss_coarse_to_fine()`. Convert qualified modes with
`observations_from_search()` and feed them chronologically to a separately bound
`PssTracker` for each receiver/channel/clock geometry.

## Tools and reproducible workflows

| Latest change | Path | Capability | Reads/writes production state? |
|---|---|---|---|
| 2026-08-31 | `tools/replay_pss_frame_timing.py` | Rate-generic replay on recorded IQ; writes candidate timing JSON | Read-only IQ; report output only |
| 2026-08-31 | `tools/plot_pss_frame_timing_replay.py` | Detection/timing-mode plots from replay JSON | No IQ or production writes |
| 2026-09-15 | `tools/replay_scanner_pss_bandwidth.py` | Deterministic adaptive-IQ replay comparing native 10 MS/s with ideal same-ADC derived 2.5 MS/s; causal tracker; aggregate CSV/JSON/figures | Read-only sealed IQ; report output only |
| 2026-09-15 | `tools/qualify_pss_bandwidth.py` | Full-budget noise, tone, and pilot-only negative controls | Synthetic controls only |
| 2026-09-02 | `tools/report_6f8_pss_glrt_deep_dive.py` | Reconstructs persisted PSS tracks, timing steps, rate/sign agreement, and GLRT overlap for capture `6f8` | Existing products only |
| 2026-09-02 | `tools/report_7fea_pss_glrt_deep_dive.py` | Native-PSS/GLRT rate, continuity, timing residual, and duplicate-track diagnostics for `7fea` | Existing products only |
| 2026-09-03 | `tools/analyze_0181_native25_fractional_glrt.py` | Independently re-runs native-25 fractional GLRT on PSS-supported windows and compares with 2.5 MS/s GLRT/PSS | Read-only IQ; report output only |

## Test inventory

| Latest change | Test path | Coverage |
|---|---|---|
| 2026-09-02 | `tests/analysis/test_pss_timing.py` | Published waveform digest, projections, search inputs, candidate separation, fractional windows, and compatibility |
| 2026-09-01 | `tests/analysis/test_pss_search.py` | Projection geometry, CFO banks, de-duplication, continuity, association, and track fitting |
| 2026-09-15 | `tests/analysis/test_pss_bandwidth.py` | Partial/asymmetric overlap, response model, arbitrary-rate templates, convergence, unsupported hypotheses, and coarse-to-fine budgets |
| 2026-09-15 | `tests/analysis/test_pss_tracker.py` | Causal state transitions, circular phase, uncertainty, ambiguity, source isolation, gaps, expiry, and reacquisition |
| 2026-09-02 | `tests/analysis/test_standard_native_pss.py` | Standard-native validity, binding, blind/conditioned lineage, product construction, and deterministic accounting |
| 2026-09-06 | `tests/analysis/test_standard_native_pss_glrt_comparison.py` | Common-coordinate signs and comparison rendering |
| 2026-09-15 | `tests/analysis/test_replay_scanner_pss_bandwidth.py` | Frozen replay selection, matched bandwidth arms, controls, archive, and aggregation |

## Report chronology and what each added

| Report date | Report | Main PSS contribution |
|---|---|---|
| 2026-08-25 | `2026_08_25_multi_dwell_pss_sss_doppler.md` | Early multi-dwell PSS/SSS and Doppler comparison; established that synchronization evidence and carrier evidence must remain distinct |
| 2026-08-31 | `2026_08_31_071200_pss_timing_glrt_comparison.md` | Rate-generic PSS frame timing, causal comparison with GLRT, and explicit candidate-only interpretation |
| 2026-08-31 | `2026_08_31_production_dual_2p5_25_pss_replay.md` | Mixed-rate 2.5/25 MS/s replay; found a coherent candidate episode on one receiver and negative/partial paths on others |
| 2026-09-02 | `2026_09_02_five_paired_native25_pss_vs_2p5_glrt.md` | Five paired captures; native-25 PSS timing versus low-rate GLRT with exact source pairing |
| 2026-09-12 | `2026_09_12_fractional_pss_peak_fix.md` | Corrected fractional PSS peak handling and documented the effect on timing residuals |
| 2026-09-12 | `2026_09_12_pss_glrt_timing_residuals.md` | Separated raw, fitted, heldout, and conditional timing residual claims; documented continuity limits |
| 2026-09-12 | `2026_09_12_pss_mixture_models.md` | Modelled competing timing modes/outlier bands and retained abstention rather than forcing one peak |
| 2026-09-15 | `2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle.md` | Added reusable bandwidth-aware replay: native 10 MS/s produced more candidate-bearing visits than derived 2.5 MS/s, but pilot-only controls prevented a verified-PSS claim |
| 2026-09-18 | `2026_09_18_sixteen_hour_rx0_multirate_pss_glrt_tle.md` | Confirmed that current 10/15/20 MS/s adaptive production sessions contain no persisted PSS products; only GLRT can be compared in-window |

The September 12 report directories contain frozen copies of source modules and
tests under `reports/figures/.../source/`. Those copies preserve exact report
provenance. They are not additional live implementations and should not be
edited or imported.

## Capability gaps

The code can search and causally track PSS-like timing modes over arbitrary
bandwidth and frequency offset. It cannot yet declare verified PSS because the
current acceptance policy does not reject repeating edge-pilot interference.
The adaptive scanner does not schedule or persist PSS evidence, so current
10/15/20 MS/s sessions cannot be compared for PSS without bounded replay.
Absolute instrument delay and measured analogue passband response also remain
external calibration inputs. No PSS module currently assigns a Starlink
satellite identity.
