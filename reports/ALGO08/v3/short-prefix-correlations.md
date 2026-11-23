# Reuse the signed short verifier's exact CFO prefix

The original 12 ms primary supplied all eight exact prefix frames on **99 of 100** staged short positives. The guarded native handoff then ran the original correlator only on the remaining frames. The held 45-positive refinement cost fell from **24.917 to 11.867 CPU ms**. Across dense, weak and held inputs, the median paired saving was **280–291 µs per original positive**. All eight diagnostic doubles and every final factor in all six paired repeats matched the frozen independent-gather result bit for bit. [Frozen identity audit](short-prefix-correlations-protocol.md) · [Paired timing protocol](short-prefix-refine-protocol.md) · [Full receipts](measurements/short-prefix-correlations.json.gz)

## Which rows can be carried forward?

The installed short GLRT uses eight groups of 64 symbols, with 44 pilot taps per symbol and each pilot frame starting at `epoch + floor((40000*f+1)/3)`. Fractional positions use the same Float64 additions, flooring and 16-tap Lanczos support as the long reference. The current pinned primary's verifier actually requests the absolute exact phase path. Its caller selects a symbol named `portable_verifier_factor`, whose implementation passes `allow_phase_free=0`. An alternate receiver with relative phase folding would need a different proof. The audit captured the untouched short binary's final native exact and rolled correlation arrays and independently gathered the original long rows.

| Staged scope | Short lanes | Positives | Same scout and reported CFO | Exact frames available / tested | All full-refiner frames |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 dense, first 24 visits | 32 | 21 | 21 | 168 / 168 | 314 |
| DS26 weak, 18 stereo clips | 36 | 34 | 33 | 264 / 272 | 501 |
| DS30-0169 held, first member | 86 | 45 | 45 | 360 / 360 | 665 |

Each frame comparison checks both 64-symbol pilot rows. Across all panels, the ninth reference frame was entirely inside the short acquisition in **80** cases and crossed the boundary in **20**. The short verifier had omitted it under its eight-frame cap. That frame and every later frame remain independently gathered. The eight available rows represent **54.05%** of the original compiled tap support before gating, or **53.51%** after the measured independent fallback.

One weak reported CFO differed from its actual scout carrier by **−443.89 Hz**. The first eight rows matched the independent reference at the scout CFO. At the reported CFO, every frame failed the exact check. Applying a symbol-center phase correction without rereading those taps gave a relative complex RMS error of **0.00349** and changed the full and prefix residuals by about **0.566 Hz** and **0.953 Hz** in magnitude. The original rule fell back on that lane, so its emitted factor happened to agree. The phase error evolves within a 44-tap symbol, where the stored sum cannot reconstruct the independently weighted taps. The timed implementation uses the exact full gather for this lane and any failed compatibility guard. [Prior exact gather](short-cfo-exact-cost.md)

## Paid callback and lane clocks

The wrapper calls the previously released primary and immediately passes its resident state to the refiner with the same measured lane, waveform, pilot, timing and scout CFO. The refiner checks bitwise carrier identity, exact phase mode and both support bounds. It independently measures any later frame with the original signed phases, copies the original eight exact and rolled rows, then runs the original score and acceptance rule in original order. The absolute Lanczos fractional state depends on each rounded sample position. Restarting its table for later frames changes row indices, while every used weight and complex term retains the original arithmetic. An unavailable refinement retains the original admitted factor.

| Staged scope | Independent callback CPU, ms | Reused callback CPU, ms | Median paired saving per positive, µs | Entire paid short lanes, median elapsed ms |
| --- | ---: | ---: | ---: | ---: |
| Dense | 11.656 | 5.540 | 288.76 | 48.190 → 41.190 |
| Weak | 18.475 | 8.980 | 279.67 | 63.326 → 53.368 |
| Held | 24.917 | 11.867 | 290.64 | 119.864 → 107.136 |

The callback CPU includes the guard, remaining gather and correlations, prefix copying, delay products and scores. The short-lane clock adds actual scout and verifier work, every empty lane, Python rule evaluation and emitted factor handling. Three passes in each order ran on one Gauss core, with one independent fallback per weak pass and no fallback elsewhere. All **54** originally empty lanes remained empty. Setup took **0.825 s wall** for the benchmark libraries and the audit-only helper was built separately. Signed tmpfs intake ran outside the timing with no block-storage input. Full anchor lanes, compressed-input traversal, publication and solving are outside these clocks.

The dense measured per-positive saving projects to **1.84 CPU seconds** at 6,380 positives if this work and exact-eligibility mix transfer. This is a projection for the refinement addition, with no new whole-recording, position or cold-storage measurement. The direct-kernel recurrence experiment is separate.

## Reproduce and integrate

The existing archive-readable account can run `python -BP -m reports.ALGO08.v3.short_prefix_correlations NEW_TMPFS_AUDIT` and `python -BP -m reports.ALGO08.v3.short_prefix_benchmark NEW_TMPFS_BENCH` under the single shared Gauss lock, CPU 2, nice 15, I/O priority 7 and single numerical threads. The second driver verifies the exact first receipt. Both use the existing staged weak zip and the original signed dense and held tmpfs members. No original waveform data was read. The first benchmark preflight stopped while verifying the replaced wrapper object, which does not enter the new link. The retained run verifies every reused object and the original source of the replacement. Twenty boundary and adjacent tests passed, including both pilot edges, both carrier polarities, integer and fractional support, and independent fallback for a changed seed.

The two verified prototype exports are `short_primary_and_cfo` in the short wrapper and `short_cfo_reuse` in the full verifier extension. The original full verifier workspace and the short verifier must come from the same pinned pilot asset. The consumed pointer remains local to the just-completed native primary call. The measured binaries are `52cf2d62b6bde206a7d8bd2647c4910c0f271256da675347201c49edbc7234b9` for the short wrapper and `6f007dfe0f92706f1fdd41fae89e5821ab98f646de1e337e0e73139072d8cd28` for the full extension. [Handoff and benchmark](short_prefix_benchmark.py) · [Native fallback and reuse](short_prefix_refine.inc) · [Component tests](../../../tests/pipeline_eval/test_short_prefix_correlations.py)
