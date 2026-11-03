# Corrected wideband detector stage profile

This report extracts the existing stage-boundary timers for DS9 visit 301. It
does not add timers to a sample loop, rebuild the detector, or change an
algorithm. The physical ARM output and its corrected-host comparison were
already frozen by `../corrected-wideband-arm-v1`.

The input is one 120 ms, 7.5 MS/s visit with both receivers. The physical ARM
call used 55,300.005 ms wall and 55,286.790 ms CPU. Of 55,250.087 ms summed row
CPU:

| disjoint stage | ARM CPU ms | share of row CPU | host CPU ms | ARM / host |
|---|---:|---:|---:|---:|
| coarse interval search | 46,015.884 | 83.29% | 709.322 | 64.87x |
| integer acquisition/refinement | 8,659.451 | 15.67% | 75.568 | 114.59x |
| fractional epoch refinement | 491.891 | 0.89% | 6.269 | 78.47x |
| final scoring/control/sort residual | 82.862 | 0.15% | 0.925 | — |

The integer acquisition/refinement interval contains these nested timers:

| acquisition substage | ARM CPU ms | acquisition share | host CPU ms | ARM / host |
|---|---:|---:|---:|---:|
| fine FFT | 1,461.995 | 16.88% | 12.537 | 116.62x |
| conditioned CFO search | 6,866.980 | 79.30% | 59.011 | 116.37x |
| verification | 329.729 | 3.81% | 3.996 | 82.51x |
| loop/control remainder | 0.747 | 0.01% | 0.024 | — |

Final integer GLRT is 73.346 ms ARM and 0.798 ms host. It is part of the
top-level final residual, outside acquisition, so it must not be added to the
acquisition subtotals. At the outer call level, physical ARM preparation used
35.080 ms and search used 55,250.499 ms; allocation, proposal setup, and cleanup
together used 0.038 ms.

The decisive absolute cost is the coarse interval search at about 46.0 seconds
for this visit. Conditioned CFO search is the next largest cost at about 6.87
seconds. The latter has a larger ARM/host multiplier, but optimizing it alone
cannot approach real time while coarse remains unchanged. The measured wall
time is about 460.8 times the 120 ms recording duration.

Scientific output remained bound to the existing comparison: 16 candidates
had equal structure and stayed within frozen tolerance, all 12 comparable gate
decisions agreed, and 7 candidates passed. These measurements therefore locate
cost within that already verified execution; they do not qualify a new
algorithm or a population-wide performance bound.

Run the extractor from the repository root:

```sh
reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-stage-profile-v1/summarize.py \
  > /tmp/stage-profile.json
cmp /tmp/stage-profile.json \
  reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-stage-profile-v1/stage-profile.json
```

`stage-profile.json` retains per-receiver values, nested-stage semantics,
evidence hashes, and the single-run interpretation limits.
`coarse-source-audit.md` traces the frozen inner loops and defines the smallest
exact-semantics optimization experiment; it does not assign unmeasured time to
an inner operation.
