# Position error by receiver modification

Each page compares a modification with v5 on exactly the same recordings. Most pages cover 127 DS26 and eight DS29 recordings. The full-IQ and partial-IQ replays cover one recording per dataset. The live reduced v5 fit covers three per dataset.

The upper plots count all recordings. The lower plots show each returned estimate
and mark its median with a diamond. The four original v5 configurations are
shown on every page. A forced estimate includes the best guess when a fix is withheld.

**Fitted calibration**  [View every chart](fitted_c/README.md) · [Figure book](fitted_c/modifications.pdf) · [Source rows](fitted_c/modifications.csv)

**Zero calibration**  [View every chart](c0/README.md) · [Figure book](c0/modifications.pdf) · [Source rows](c0/modifications.csv)

Fix counts use fitted calibration and the four-region decision when available. Single-tile receivers use their original tile. Median and P95 use published fixes.

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
| Alternative native GLRT with the v5 solver | 1/1 · 0.186 · 0.186 | 1/1 · 2.662 · 2.662 | [Figure](fitted_c/native-to-v5.png) | [Figure](c0/native-to-v5.png) |
| V5 stopped after the initial satellite assignment | 127/127 · 1.297 · 4.542 | 8/8 · 0.968 · 3.292 | [Figure](fitted_c/v5_stop_initial.png) | [Figure](c0/v5_stop_initial.png) |
| V5 stopped after the conservative refit | 127/127 · 1.130 · 3.977 | 8/8 · 1.341 · 2.377 | [Figure](fitted_c/v5_stop_conservative.png) | [Figure](c0/v5_stop_conservative.png) |
| V5 stopped after the satellite-family refit | 127/127 · 1.020 · 3.466 | 8/8 · 0.718 · 1.640 | [Figure](fitted_c/v5_stop_family.png) | [Figure](c0/v5_stop_family.png) |
| V5 stopped after the signed orbit correction | 127/127 · 1.018 · 3.338 | 8/8 · 0.742 · 1.650 | [Figure](fitted_c/v5_stop_signed.png) | [Figure](c0/v5_stop_signed.png) |
| V5 stopped after the cavity fit | 127/127 · 0.999 · 3.126 | 8/8 · 0.742 · 1.312 | [Figure](fitted_c/v5_stop_cavity.png) | [Figure](c0/v5_stop_cavity.png) |
| Reduced v5 through the cavity fit | 3/3 · 0.747 · 1.162 | 3/3 · 0.917 · 1.404 | [Figure](fitted_c/v5_core.png) | [Figure](c0/v5_core.png) |
| Doppler fit with shared receiver and satellite corrections | 92/127 · 2.004 · 5.207 | 6/8 · 2.034 · 5.063 | [Figure](fitted_c/shared_doppler.png) | [Figure](c0/shared_doppler.png) |
| Accelerated pilot acquisition with the v5 position fit | 1/1 · 1.208 · 1.208 | 1/1 · 0.517 · 0.517 | [Figure](fitted_c/anchor_receiver.png) | [Figure](c0/anchor_receiver.png) |

The lean v5 trial extracts positions from archived numerical fits on DS26. The full numerical fit was rerun on the 16-recording panel. The four raw-IQ changes use 80 scheduled windows per recording. Streamed IQ decoding and bounded raw-IQ replay share the same measured native detector and downstream position decision.
