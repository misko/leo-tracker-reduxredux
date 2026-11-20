# Position error by receiver modification

[Browse individual charts](index.html)

Each page compares a modification with v5 on exactly the same recordings. The chart headings give the dataset and number of recordings. Both roof datasets come from the same receiver site.

The 127 common DS26 recordings had successful runs under every original v5 option in both repeats. The eight DS29 recordings come from the original blind panel. These charts score subsequent experiments retrospectively on that panel.

The upper plots count all recordings. The lower plots show each returned estimate
and mark its median with a diamond. The four original v5 configurations are
shown on every page. A forced estimate includes the best guess when a fix is withheld.

**Fitted calibration**  [View every chart](fitted_c/README.md) · [Figure book](fitted_c/modifications.pdf) · [Source rows](fitted_c/modifications.csv)

**Zero calibration**  [View every chart](c0/README.md) · [Figure book](c0/modifications.pdf) · [Source rows](c0/modifications.csv)

Fix counts use fitted calibration and the four-region decision when available. Other rows use the decision described on their chart. Median and P95 use published fixes.

| Modification | DS26 fixes · median km · P95 km | DS29 fixes · median km · P95 km | Fitted calibration | Zero calibration |
|---|---|---|---|---|
| V5 without evidence rendering | 127/127 · 0.999 · 3.126 | 8/8 · 0.742 · 1.312 | [Figure](fitted_c/v5_lean.png) | [Figure](c0/v5_lean.png) |
| Batched pilot-bank GLRT | 0/127 | 0/8 | [Figure](fitted_c/glrt_batch.png) | [Figure](c0/glrt_batch.png) |
| Streamed IQ decoding | 0/127 | 0/8 | [Figure](fitted_c/iq_stream.png) | [Figure](c0/iq_stream.png) |
| Early screening in the pilot-bank GLRT | 0/127 | 0/8 | [Figure](fitted_c/glrt_cascade.png) | [Figure](c0/glrt_cascade.png) |
| Reusing orbital states | 71/127 · 2.677 · 5.634 | 5/8 · 4.076 · 6.129 | [Figure](fitted_c/orbit_interp.png) | [Figure](c0/orbit_interp.png) |
| Horizon screening for Doppler scoring | 71/127 · 2.677 · 5.634 | 5/8 · 4.076 · 6.129 | [Figure](fitted_c/shape_score.png) | [Figure](c0/shape_score.png) |
| Compressing Doppler tracks | 71/127 · 2.677 · 5.197 | 5/8 · 4.076 · 6.129 | [Figure](fitted_c/track_reduce.png) | [Figure](c0/track_reduce.png) |
| Causal track linking | 68/127 · 2.723 · 5.446 | 4/8 · 3.193 · 5.514 | [Figure](fitted_c/track_link.png) | [Figure](c0/track_link.png) |
| Position from bounded raw-IQ replay | 0/127 | 0/8 | [Figure](fitted_c/iq_position.png) | [Figure](c0/iq_position.png) |
| Fitting position with per-track offsets removed | 0/127 | 0/8 | [Figure](fitted_c/projected_fit.png) | [Figure](c0/projected_fit.png) |
| Full ordinary native GLRT with the v5 solver | 3/3 · 0.821 · 1.211 | 3/3 · 1.225 · 2.518 | [Figure](fitted_c/native-to-v5.png) | [Figure](c0/native-to-v5.png) |
| V5 stopped after the initial satellite assignment | 127/127 · 1.297 · 4.542 | 8/8 · 0.968 · 3.292 | [Figure](fitted_c/v5_stop_initial.png) | [Figure](c0/v5_stop_initial.png) |
| V5 stopped after the conservative refit | 127/127 · 1.130 · 3.977 | 8/8 · 1.341 · 2.377 | [Figure](fitted_c/v5_stop_conservative.png) | [Figure](c0/v5_stop_conservative.png) |
| V5 stopped after the satellite-family refit | 127/127 · 1.020 · 3.466 | 8/8 · 0.718 · 1.640 | [Figure](fitted_c/v5_stop_family.png) | [Figure](c0/v5_stop_family.png) |
| V5 stopped after the signed orbit correction | 127/127 · 1.018 · 3.338 | 8/8 · 0.742 · 1.650 | [Figure](fitted_c/v5_stop_signed.png) | [Figure](c0/v5_stop_signed.png) |
| V5 stopped after the cavity fit | 127/127 · 0.999 · 3.126 | 8/8 · 0.742 · 1.312 | [Figure](fitted_c/v5_stop_cavity.png) | [Figure](c0/v5_stop_cavity.png) |
| Reduced v5 through the cavity fit | 3/3 · 0.747 · 1.162 | 3/3 · 0.917 · 1.404 | [Figure](fitted_c/v5_core.png) | [Figure](c0/v5_core.png) |
| Doppler fit with shared receiver and satellite corrections | 92/127 · 2.004 · 5.207 | 6/8 · 2.034 · 5.063 | [Figure](fitted_c/shared_doppler.png) | [Figure](c0/shared_doppler.png) |
| Accelerated pilot acquisition with the v5 position fit | 1/1 · 1.208 · 1.208 | 1/1 · 0.517 · 0.517 | [Figure](fitted_c/anchor_receiver.png) | [Figure](c0/anchor_receiver.png) |
| V5 using all visits to odd RF channels | 3/3 · 1.191 · 1.794 | 3/3 · 1.253 · 1.363 | [Figure](fitted_c/glrt_odd_channels.png) | [Figure](c0/glrt_odd_channels.png) |
| V5 using all visits to even RF channels | 3/3 · 1.919 · 4.843 | 3/3 · 3.963 · 14.188 | [Figure](fitted_c/glrt_even_channels.png) | [Figure](c0/glrt_even_channels.png) |
| V5 with compact orbital projection | 127/127 · 0.999 · 3.126 | 8/8 · 0.742 · 1.312 | [Figure](fitted_c/orbit_projector.png) | [Figure](c0/orbit_projector.png) |
| Streaming Doppler tracker | 8/8 · 3.403 · 8.708 | Untested | [Figure](fitted_c/early_stream.png) | [Figure](c0/early_stream.png) |
| Guided pilot search with blind reacquisition | 8/8 · 4.361 · 7.222 | Untested | [Figure](fitted_c/early_pilots.png) | [Figure](c0/early_pilots.png) |
| Satellite-family consensus | 8/8 · 4.900 · 9.507 | Untested | [Figure](fitted_c/early_consensus.png) | [Figure](c0/early_consensus.png) |
| Packed Doppler orbit table | 8/8 · 5.018 · 7.595 | Untested | [Figure](fitted_c/early_compact.png) | [Figure](c0/early_compact.png) |
| Stationary site forecast from prior fixes | 8/8 · 1.855 · 2.406 | Untested | [Figure](fitted_c/early_stationary.png) | [Figure](c0/early_stationary.png) |
| 12 tracks chosen by geometry | 8/8 · 2.355 · 3.082 | Untested | [Figure](fitted_c/early_coreset.png) | [Figure](c0/early_coreset.png) |
| Doppler changes only | 8/8 · 5.130 · 8.282 | Untested | [Figure](fitted_c/early_differences.png) | [Figure](c0/early_differences.png) |
| Marginalized position grid | 8/8 · 4.624 · 9.392 | Untested | [Figure](fitted_c/early_grid.png) | [Figure](c0/early_grid.png) |
| Pass-event timing only | 0/8 | Untested | [Figure](fitted_c/early_events.png) | [Figure](c0/early_events.png) |
| Tiny coordinate network | 8/8 · 3.253 · 9.498 | Untested | [Figure](fitted_c/early_network.png) | [Figure](c0/early_network.png) |
| Observe alternate complete eight-channel sweeps | 3/3 · 0.654 · 2.633 | 3/3 · 1.558 · 3.164 | [Figure](fitted_c/sweep_schedule.png) | [Figure](c0/sweep_schedule.png) |
| Verify satellite assignments on later Doppler samples | 100/127 · 3.643 · 6.741 | 7/8 · 5.343 · 5.983 | [Figure](fitted_c/arc_validation.png) | [Figure](c0/arc_validation.png) |
| Compact v5 with the final position repairs | 3/3 · 1.208 · 1.217 | 1/1 · 0.517 · 0.517 | [Figure](fitted_c/compact_finish.png) | [Figure](c0/compact_finish.png) |
| Full v5 with bytewise orbital element checksums | 1/1 · 1.208 · 1.208 | 1/1 · 0.517 · 0.517 | [Figure](fitted_c/catalogue_checksum.png) | [Figure](c0/catalogue_checksum.png) |
| Reorder the pilot correlation sums before the v5 fit | 1/1 · 1.208 · 1.208 | 1/1 · 0.517 · 0.517 | [Figure](fitted_c/pilot_kernel.png) | [Figure](c0/pilot_kernel.png) |
| Native wideband pilot acquisition on 20 ms visits | Wideband GLRT · sampled IQ · 1/1 · 1.208 · 1.208<br>Capture-era GLRT · stock · 1/1 · 1.208 · 1.208 | Wideband GLRT · sampled IQ · 1/1 · 0.517 · 0.517<br>Capture-era GLRT · stock · 1/1 · 0.517 · 0.517 | [Figure](fitted_c/native_geometry.png) | [Figure](c0/native_geometry.png) |
| Native fractional winner gate with the v5 solver | 3/3 · 1.267 · 1.371 | 3/3 · 1.213 · 2.556 | [Figure](fitted_c/native_winner.png) | [Figure](c0/native_winner.png) |
| Full raw replay through one physical receiver input | 1/1 · 6.008 · 6.008 | 1/1 · 2.157 · 2.157 | [Figure](fitted_c/single_rx0.png) | [Figure](c0/single_rx0.png) |
| RX0 position from two archived detector sources | RX0 · capture-era factors · 1/1 · 1.535 · 1.535<br>RX0 · ordinary native factors · 1/1 · 6.008 · 6.008 | RX0 · capture-era factors · 1/1 · 1.147 · 1.147<br>RX0 · ordinary native factors · 1/1 · 2.157 · 2.157 | [Figure](fitted_c/single_rx0_factors.png) | [Figure](c0/single_rx0_factors.png) |
| Late pilot confirmation at the proposed epoch and CFO | Pilot gate · sampled visits · 1/1 · 0.245 · 0.245<br>Ordinary native GLRT · stock · 1/1 · 0.186 · 0.186<br>Pilot gate · all visits · 1/1 · 0.247 · 0.247 | Pilot gate · sampled visits · 1/1 · 2.662 · 2.662<br>Ordinary native GLRT · stock · 1/1 · 2.662 · 2.662<br>Pilot gate · all visits · 1/1 · 2.681 · 2.681 | [Figure](fitted_c/pilot_confirmation.png) | [Figure](c0/pilot_confirmation.png) |
| Shared sliding tones for coarse pilot acquisition | Sliding tones · sampled IQ · 1/1 · 1.208 · 1.208<br>Capture-era GLRT · stock · 1/1 · 1.208 · 1.208 | Sliding tones · sampled IQ · 1/1 · 0.517 · 0.517<br>Capture-era GLRT · stock · 1/1 · 0.517 · 0.517 | [Figure](fitted_c/spectral_grid.png) | [Figure](c0/spectral_grid.png) |
| Longitude controls on Doppler arc predictions | Untested | 7/8 · 5.343 · 5.983 | [Figure](fitted_c/off_region_test.png) | [Figure](c0/off_region_test.png) |
| Cold-start localization by GLRT point voting | Global search · published · 0/3<br>Supplied tile · published · 0/3 | Global search · published · 0/3<br>Supplied tile · published · 0/3 | [Figure](fitted_c/point_votes.png) | [Figure](c0/point_votes.png) |
| Cold-start localization from GLRT rate triplets | Global search · published · 0/3<br>Supplied tile · published · 0/3 | Global search · published · 0/3<br>Supplied tile · published · 0/3 | [Figure](fitted_c/rate_triplets.png) | [Figure](c0/rate_triplets.png) |
| Cold-start localization from folded GLRT Doppler | Global search · published · 1/3 · 8430.970 · 8430.970<br>Supplied tile · published · 2/3 · 2.924 · 3.915 | Global search · published · 0/3<br>Supplied tile · published · 1/3 · 6.378 · 6.378 | [Figure](fitted_c/folded_doppler.png) | [Figure](c0/folded_doppler.png) |
| Batched salvage in the compact v5 finish | Batched salvage · published · 1/1 · 1.208 · 1.208<br>Compact v5 · matched stock · 1/1 · 1.208 · 1.208 | Batched salvage · published · Untested<br>Compact v5 · matched stock · Untested | [Figure](fitted_c/v5_batched_salvage.png) | [Figure](c0/v5_batched_salvage.png) |
| Batched ECEF propagation in the compact v5 finish | Batched catalogue · published · 1/1 · 1.208 · 1.208<br>Compact v5 · matched stock · 1/1 · 1.208 · 1.208 | Batched catalogue · published · 1/1 · 0.517 · 0.517<br>Compact v5 · matched stock · 1/1 · 0.517 · 0.517 | [Figure](fitted_c/v5_catalogue_memory.png) | [Figure](c0/v5_catalogue_memory.png) |
| Compact v5 with incremental GLRT input preparation | Incremental reader · published · 1/1 · 1.208 · 1.208<br>Compact v5 · matched stock · 1/1 · 1.208 · 1.208 | Incremental reader · published · 1/1 · 0.517 · 0.517<br>Compact v5 · matched stock · 1/1 · 0.517 · 0.517 | [Figure](fitted_c/v5_stream_prepare.png) | [Figure](c0/v5_stream_prepare.png) |
| Position from Doppler pass geometry | Global search · published · 0/1<br>Supplied tile · published · 1/1 · 3.224 · 3.224 | Global search · published · 0/1<br>Supplied tile · published · 0/1 | [Figure](fitted_c/pass_geometry.png) | [Figure](c0/pass_geometry.png) |

The lean v5 trial extracts positions from archived numerical fits on DS26. The full numerical fit was rerun on the 16-recording panel.

The four bounded raw-IQ changes use 80 scheduled windows per recording. Streamed IQ decoding and bounded raw-IQ replay share the same measured native detector and downstream position decision.
