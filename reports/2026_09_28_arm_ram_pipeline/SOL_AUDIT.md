# Independent scientific parity audit

This audit compares the isolated ARM outputs from original method D with
`goal40mag` for all 28 saved DS7 dwell cases. Each case was run three times,
giving 56 unique receiver results and 168 receiver observations. The inherited
ARM assessor passes every unique receiver result and every repeated result.

| Rate | Unique dwells | Unique RX results | D positives retained | Lost / added | Identity failures | Max timing error | Max CFO error |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 16 | 32 | 20 / 20 | 0 / 0 | 0 | 9.095e-14 us | 0 Hz |
| 5 MS/s | 4 | 8 | 4 / 4 | 0 / 0 | 0 | 9.095e-14 us | 0 Hz |
| 7.5 MS/s | 4 | 8 | 3 / 3 | 0 / 0 | 0 | 0 us | 0 Hz |
| 10 MS/s | 4 | 8 | 4 / 4 | 0 / 0 | 0 | 0 us | 0 Hz |
| **All rates** | **28** | **56** | **31 / 31** | **0 / 0** | **0** | **9.095e-14 us** | **0 Hz** |

All 56 threshold decisions match. Across the unique results, 2,962 categorical
and selection values were compared exactly with no mismatch. These include rank
and screen orders, projected epochs, selected screen and window, confirmation
mask and count, candidate count, fractional-completion state, nuisance flags,
and integer candidate and proposal epochs. Each method also produced bit-identical
science across its three cycles after timer fields were removed.

The largest exact/control/margin differences are `2.331e-15`, `2.290e-16`, and
`2.331e-15`. The largest other differences are:

- rank or screen score: `0.0230148` (`2.46e-7` relative at that cell)
- screen contrast: `3.4356e-7`
- coarse score: `1.1303e-7`
- conditioned score: `5.0926e-8`
- fractional timing offset: `8.4821e-14` samples

The host sanitizer matrix independently passed both isolated and concurrent
modes at all four rates. Each mode covered 16 receiver cases, retained all 9
original-D positives, had no added positives or decision changes, and had zero
timing or CFO error. For each binary, isolated and concurrent scientific output
was bit-identical after removing timer fields.

The per-core `/proc/stat` results cannot provide a reliable inclusive-headroom
gate for this experiment. The target uses periodic HZ=100 tick accounting, while
the producer runs every 10 ms. Depending on phase, CPU1 was charged only 8–9
busy ticks or all 1,440 ticks for essentially the same 1.19–1.28 seconds of
precise producer thread CPU. CPU0 is less severely affected but shows the same
aliasing. Precise consumer thread CPU divided by the ingestion duration is the
valid workload-budget measure; inclusive IRQ and background-load headroom remains
unproven by these receipts.

This evidence applies only to the native six-window rank plus one-confirmation
kernel. It does not measure the full server eleven-window, eight-candidate
pipeline and cannot support its individual-positive 80% or 90% recovery targets.
The RAM producer also does not model DMA, IIO, RF, interrupts, or live adaptive
feedback.

Machine-readable results, per-rate gates, source receipt hashes, and every
numeric maximum are in `SOL_AUDIT.json`.
