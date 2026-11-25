# What the faster short verifier buys on the first 64 DS30 recordings

The verified ALGO08v3 and mixed-aperture candidate runs took **6,311.33 and 3,764.93 seconds** across the same 64 recordings. The 2× target requires saving another **609.27 seconds**. The candidate issued **601,764** short callbacks. Of these, 282,248 returned a detection and 319,516 returned empty. Those calls consumed 683.06 process CPU seconds and 751.12 elapsed seconds. [Frozen stage clocks](first64-producer-transfer.md) · [Per-recording call counts and calculations](measurements/short-phase-first64.json.gz)

The new verifier reuses the carrier-phase table from the integer search during fractional timing refinement. We applied its measured positive and empty callback savings to each recording’s actual mix. The projections below assume each CPU second saved reduces elapsed time by one second. They hold other operations and outcomes fixed, including the map calculation. [Paired native measurements](short-shared-integer-phase.md)

| Change applied to the first 64 recordings | Seconds saved | Summed speedup | Median paired speedup | Seconds still needed for 2× summed |
|---|---:|---:|---:|---:|
| Measured field runs | 0 | 1.676× | 1.732× | 609.27 |
| Projected kernel savings from 36 DS30-0163 lanes | 50.89 | 1.699× | 1.758× | 558.38 |
| Projected kernel savings from six DS30-0419 lanes | 57.19 | 1.702× | 1.761× | 552.08 |
| DS30-0163 kernel estimate plus DS30-0049 input-buffer estimate | 130.85 | 1.737× | 1.797× | 478.41 |
| DS30-0163 kernel estimate plus DS30-0016 input-buffer estimate | 362.00 | 1.855× | 1.924× | 247.27 |

The DS30-0163 timings come from six paired rounds on ten positive and 26 empty lanes. Using both outcome prices from the same round gives 41.91–54.38 seconds saved across the field sample. Those repeats describe timing variation on the same 36 lanes. DS30-0419 contributes an independent six-lane sample. The callback trials retained all discrete outputs across the two recordings, with small changes in score rounding. End-to-end position accuracy for this kernel still requires a full original replay. [Kernel receipt](measurements/short-shared-integer-phase.json)

The input-buffer projections use the earlier per-recording transport estimates scaled by authenticated bytes. DS30-0049 contributes producer CPU credited as wall time. DS30-0016 contributes the change in acquisition wall time after subtracting the change in native callback time. It used a combined trial with different page faults in each arm, which limits attribution. The separate checked map exporter failed a numerical tolerance and receives no credit here. [Input transfer scope](first64-producer-transfer.md) · [Map comparison](profiled-grid-export-south.md)

With everything outside the short callback held fixed, both timing gates require a uniform **81.1% reduction** in short-callback elapsed time. Eliminating the entire short callback would reach 2.094× summed. The DS30-0163 component estimate covers about one twelfth of the total deficit. [Reproducer](short_phase_field_cost.py)
