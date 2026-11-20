# Position error for each receiver modification

The complete roof benchmark has 38 pages. Every page compares one modification with the four original v5 configurations on the same recordings. The two books use matched calibration settings. Each chart has a cumulative error curve, individual position estimates, and fix counts. [Fitted calibration PDF](figures/fitted_c/modifications.pdf) · [Zero calibration PDF](figures/c0/modifications.pdf) · [Individual charts and percentiles](figures/README.md) · [Recording-level errors](figures/fitted_c/modifications.csv)

The original ten pipeline directions have their own book. The regional receiver comparison uses separate panels for the correct region being offered and omitted. DS26 and DS29 are recordings from one roof. StarLoc supplied tracks from a second physical installation. [Original ten directions](../2026_11_18_pipeline_eval/figures/fitted_c/modifications.pdf) · [Geographic comparisons](transfer-figures/README.md) · [Fresh blind simulation](field/confirmation/README.md)

| New modification | Matched evidence | Position charts |
|---|---|---|
| [Alternate complete eight-channel sweeps](sweep/README.md) | Kept 19,298 of 38,641 processed visits across six recordings. All six returned fixes within 5 km. Fitted median error went from 0.832 to 1.181 km and P95 from 1.395 to 3.220 km. | [Fitted](figures/fitted_c/sweep_schedule.png) · [Zero](figures/c0/sweep_schedule.png) |
| [Validate orbits on later Doppler samples](field/README.md) | On DS26, four offered regions yielded 100/127 fixes with 3.643 km median error. Full v5 on its original single tile gave 127/127 at 0.999 km. On DS29 the results were 7/8 at 5.343 km and 8/8 at 0.742 km respectively. | [Fitted](figures/fitted_c/arc_validation.png) · [Zero](figures/c0/arc_validation.png) · [Location transfer](transfer-figures/fitted_c/arc_validation.png) |
| [Compact v5 with final repairs](finish/README.md) | Reproduced the full v5 coordinates in both calibration arms on four recordings. These include two deliberately selected DS26 repair cases. On DS26-0066 the final identity correction reduced fitted error from 2.370 to 1.218 km. | [Fitted](figures/fitted_c/compact_finish.png) · [Zero](figures/c0/compact_finish.png) |
| [Bytewise orbital element checksums](catalogue/README.md) | Same coordinates and conditional frequency metrics as full numerical v5 on both smoke recordings. The checksum loop was 11.56× and 12.21× faster in the two causal catalogues. | [Fitted](figures/fitted_c/catalogue_checksum.png) · [Zero](figures/c0/catalogue_checksum.png) |
| [Reorder the pilot correlation sums](pilot/README.md) | On 16 scheduled IQ windows the detector produced identical outputs with 1.17× and 1.16× median speedups over the previous accelerated detector. Fresh compact v5 fits using those windows and archived detections for the rest reproduced both roof positions. | [Fitted](figures/fitted_c/pilot_kernel.png) · [Zero](figures/c0/pilot_kernel.png) |
| [Native wideband pilot acquisition](native-geometry/README.md) | On four real IQ windows, all 64 ranked candidates matched the capture-era detector within the stated tolerances. The native calculation used 2.82–5.53 CPU seconds per 20 ms visit. This detector-only trial has a page showing its matched v5 controls and marks candidate position as unmeasured. | [Fitted](figures/fitted_c/native_geometry.png) · [Zero](figures/c0/native_geometry.png) |

The later-sample check produced eight fixes on eleven StarLoc captures at eight nearby physical site groups. All eight fixes were within 5 km, with a median of 2.593 km and P95 of 3.874 km. It withheld on all eleven StarLoc queries with the correct region missing. The original regional receiver withheld on all eleven present and eleven missing queries. [Field scores and region decisions](field/scores.json)

A new blind simulation used 40 independently generated scenes. With the correct region offered, the later-sample check placed 16/40 receivers within 5 km and the original regional grid placed 9/40 within 5 km. With the region missing, the later-sample check published two false fixes and the grid published none. The two false fixes were 75.47 and 11,384.81 km from truth. The new calculation therefore still fails the missing-region withholding requirement. Neither simulation measured IQ processing or embedded runtime. [Fresh confirmation figure](field/confirmation/position-errors.png) · [Sealed predictions](field/confirmation/prediction-lock.json) · [Per-scene results](field/confirmation/scores.json)

To rebuild the roof and transfer books from the saved benchmark evidence, run these commands from the repository root.

```sh
.venv/bin/python -m tools.pipeline_eval figures --out /tmp/receiver-roof
.venv/bin/python -m tools.pipeline_eval figures --panel transfer124 --out /tmp/receiver-transfer
```
