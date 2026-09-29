# Wave 8 gate 0.314 plus PGO

This target workflow combines the exact-rank frontier PGO source with the
DS7-calibrated 2.5 MS/s coarse gate of 0.314.  Host704 retains 4,211/4,573
primary standard hits, above the fixed 4,116 floor, and removes 511 of 5,463
primary emitted candidates.  The gate is an explicit quality tradeoff.

The instrumented build uses stable `work/arm` paths and the unique profile
directory `/var/tmp/leo-wave8-gate314-pgo-profile`.  It requires the five
nonempty proposal core, proposal tracking, conditioned CZT, FFT, and fused
probe profiles.  The histogram and tracking units are included.

```sh
python3 reports/2026_09_29_arm_wave8_gate_pgo/build_pgo.py generate
python3 reports/2026_09_29_arm_wave8_gate_pgo/run_training.py
```

Training uses four saved contexts.  Held-out32 excludes those four for PGO,
but it comes from DS7 and is therefore not unseen relative to gate calibration.
No target runtime claim is made by the generate build.

The completed profile-use build measured **449.206119 ms per dual-RX dwell**
on PLUTO+ CPU0 over 32 dwells and all 704 scheduled windows. The matched Wave5
control took 917.632913 ms: a **51.05% reduction**, or **2.04× speedup**.
The frozen original GLRT audit recovers **849/921 positive candidate hits
(92.18%)**, with 121 unmatched positive entries. All twelve ARM units passed.
See `arm-heldout32/summary.json`, `standard-audit.json`, and
`arm-units-use.json` for the measured evidence.

This is an approximate dense-search result, not equivalence to the deployed
adaptive-scan detector. Each dwell still executes eleven overlapping 20 ms
windows per receiver. Timing includes input preparation, proposals, and search;
it excludes file transfer, initialization, and simultaneous capture. A larger
152-dwell ARM qualification is now complete: **445.352603 ms/dwell**, versus
**915.499336 ms** for a fresh matched Wave5 control (**51.35% less CPU**, 2.06×).
All 3,344 windows execute, recovering **4,211/4,573 hits (92.08%)** versus
4,506/4,573 for the control. Excluding all four PGO training contexts still
gives **51.33%** less CPU. See `arm152`, `arm152-control`, and the Wave8 report
for distributions, paired subsets, and the explicit quality tradeoff.
