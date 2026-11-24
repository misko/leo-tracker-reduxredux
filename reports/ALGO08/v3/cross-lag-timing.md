# Two timing lags can trigger exact expansion before carrier search

The rule frozen on DS30-0008 preserved every ordered native factor on DS30-0008 and on the separate held DS30-0016 first member. Short native CPU fell **18.59% and 14.71%**, respectively. Holding the original full-anchor CPU fixed gives **13.55% and 10.00%** lower matched total detector CPU including those anchors. This measurement ends at the native receiver. [Protocol](cross-lag-timing-protocol.md) · [Frozen rule](measurements/cross-lag-timing-freeze.json) · [Dense clock](measurements/cross-lag-timing-routed-dense.json.gz) · [Held weak clock](measurements/cross-lag-timing-held.json.gz)

The scout obtains independent epoch power from lags 28 and 44 and measures circular distance and each lag's best-to-next-separated peak ratio. Dense ranked policies with both features before the weak run. The cheapest dense zero-change rule uses **the smaller of the two ratios < 1.10** with the distance cutoff disabled. Undefined cues widen. The earlier single-lag rule used first/fifth and fourth/fifth ratios and repeated the broad pass. This rule checks the two lag surfaces independently before carrier, reuses both scores in their original accumulation order and computes only the remaining six original surfaces on expanded lanes. The expanded route sends the exact original twelve rows downstream. The narrow route sends four. Every lane runs one carrier and verifier pass. [Earlier single-lag trial](precarrier-timing-gate.md) · [Native routing](cross_lag_timing.inc)

| Short-clock scope | DS30-0008 development | DS30-0016 held |
|---|---:|---:|
| Original scheduled short antenna calls | 112 | 100 |
| Original positive factors, antenna 0 / 1 | 39 / 19 | 20 / 14 |
| Pinned original 12 ms CPU | 110.419 ms | 92.387 ms |
| Pinned unprotected two-lag CPU | 83.719 ms | 66.921 ms |
| Measured C routing CPU including expansions | 89.890 ms | 78.799 ms |
| Expansions, antenna 0 / 1 | 24 / 35 | 31 / 33 |
| Original factor losses in unprotected narrow arm | 8 | 12 |
| Original factor losses or additions with the frozen rule | 0 | 0 |
| Expansions on already byte-identical lanes | 51 | 52 |

The first dense development measurement priced the selected rule at 92.284 ms versus 108.999 ms for pinned original. The subsequent actual C run executes that rule without consulting factor outcomes. On the held member the same threshold is also the best zero-loss point in the prespecified hindsight grid. To reach perfect sensitivity the feature family widened at least **51 of 104 unaffected dense lanes** and **52 of 88 unaffected weak lanes**. Pairwise ranking AUC for low contrast was **0.734 dense and 0.737 weak**, versus **0.678 and 0.716** for cross-lag peak distance. An ideal chooser with the actual per-lane costs and free knowledge of which narrow output changes would cost 80.895 ms dense and 68.711 ms weak. That is a cost ceiling for better routing, not an available policy. [Dense development sweep](measurements/cross-lag-timing-development.json.gz)

Both original 64-visit members were on tmpfs and verified through the installed manifest/index, compressed/decompressed digests and frame checksum. The released signed full-anchor binary served all sixteen original anchor lanes on each member. Weak admitted 58 visits, with the original six exclusions. Dense admitted all 64. Every cue-only output matched the pinned two-lag DSO. Every forced expanded output matched the published guarded reference, including negatives and both radios. The adaptive output matched the guarded reference byte-for-byte on all **212 short lanes**. All perturbations to code apply to the 12 ms object only. The measurements sum medians of three rotated per-lane complete native call clocks. Read, decode, hash, Python dispatch and any localization solve are outside these clocks. The new and previous narrowed objects use their own PGO builds, so their standalone clock difference cannot isolate cue overhead. [Authenticated capture and scorer](cross_lag_timing.py)

## Reproduction

Use the installed numerical environment on the shared Gauss lock, CPU2, nice 15, and best-effort I/O priority 7. Under the original fixture owners run `python -Bm reports.ALGO08.v3.cross_lag_timing build BUILD ASSETS`, then `development` with a fresh JSON and `--build BUILD`. Seal that JSON before `routed-dense` or `held`, passing its path in `--frozen` and its expected digest in `--sha256`. The local DSO at `/dev/shm/leo-cross-lag-build01/short.so` has SHA-256 `abb9b25965840e491f47775a2c4b415f34948d18deec0a4bee7a6ec4703fcbe9`. The routed test sets `set_cross_lag_rule(3, 1666, 1.10)` on the executing thread. [Component tests](../../../tests/pipeline_eval/test_cross_lag_timing.py)
