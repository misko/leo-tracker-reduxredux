# 105915 long-dwell phase-change diagnostic

**Result:** a sparse, seeded random whole-window holdout predicts the existing
restored phase track better than a constant-phase model, but only modestly
better than its frozen wrong-time control. This supports conditional phase
concentration over seven seconds. It does not yet support geometric association
or position improvement.

The analysis used 16 evenly spaced rows chosen from all 704 corrected upper-edge
20 ms windows before inspecting qualification. Seed 20260923 assigned eight
whole windows to training and eight to held. Seven held windows qualified and
one abstained. A single train-only circular affine model gave:

| Quantity | Result |
| --- | ---: |
| Train-fit restored phase rate | 11.779 deg/s |
| Held coverage | 7/8 (87.5%) |
| Held median absolute circular error | 6.191 deg |
| Train-only constant control | 18.648 deg |
| Frozen wrong-time control | 8.059 deg |

The affine result clears the constant control. Its 1.87 degree advantage over
one wrong-time permutation is small and no significance threshold was frozen,
so it does not establish candidate-specific timing information. One held error
was 19.01 degrees; the other six were 2.51--8.55 degrees. All outcomes and the
abstention are retained in the JSON.

![Restored double-difference phase and sparse split](figures/2026_09_23_long_dwell_phase_change/phase-v-time.png)

The gray points show the complete previously extracted qualified curve only as
context. Colored markers are the 16 prespecified rows used here. They are
non-overlapping in raw time because their centers are about 470 ms apart.

## Authority and limits

Public `RecordingStore` inspection reconfirmed manifest digest
`sha256:2f632b9f1a1acdbcd98ac44c67fc23f583f797638b08d0ebc2afc762f99635b8`.
Stream 0 contains RX0 and RX1 on the same stored sample rows, at applied IF
1,940,312,500 Hz, 2.5 MS/s, and 2.5 MHz bandwidth. The production
`resolve_manifest_starlink_tuning()` resolver returns channel 4 upper for
stream 0 with evidence source `per_stream_manifest_tag` (and channel 2 upper
for stream 1). That manifest tag, rather than an inference from IF, authorizes
the upper-edge template used by the retained artifact. The lower-priority
capture profile does not override it.

Each original window fitted source/receiver residual carrier rotation locally
and restored its frozen carrier-model phase at the common center. The present
held split is therefore a new prediction test over an existing response
artifact, not a fresh waveform extraction. The fitted 11.779 deg/s is a
restored-model-coordinate rate conditional on the historical timing, carrier,
and source tracks. It must not be treated as independently calibrated physical
phase velocity.

The two source identities remain unverified, so this result cannot select a
physical line of sight or support a geometric claim. That does not prevent a
conditional candidate test. The next justified step is to freeze a finite
catalog candidate bank and, for every candidate pair, fit the 0.10--0.30 m
baseline vector on training windows only, then compare held circular likelihood
with candidate-swap and wrong-time controls. The candidate list, baseline
constraint, split, and selection rule must all be fixed before held scoring.
Only a candidate that predicts held phase better than those controls would
warrant stronger source qualification; absent that, this remains an instrument
and extraction stability diagnostic.

The evaluator and protocol were sealed at commit `a8c68259` before this held
evaluation. Input SHA-256 was
`261dff98f8203b4f8236ce81ccdf3c7b970d0ae2698bba13b2b72dcbf94e8c6b`.
After viewing the numerical result, the figure alone was amended to add the gray
full-track context; the split, fit, controls, and JSON metrics were unchanged.
